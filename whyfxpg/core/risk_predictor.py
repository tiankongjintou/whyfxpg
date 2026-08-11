"""
时序风险预测模块

功能：
- 基于历史风险事件时间序列，预测未来 3-12 个月的进口风险趋势
- 不依赖官方召回通知，而是基于早期信号（供应商问题、工厂审核、舆情）进行预测
- 输出：预测风险分、风险等级、置信区间、预警信号

预测方法：
- 简单移动平均（SMA）作为基线（无 ML 依赖）
- 可扩展为 Prophet / LSTM / Transformer（设计支持热插拔）
- 异常检测：事件密度超过历史均值 2σ 触发早期预警

与现有 risk_model 的区别：
  risk_model（被动）：官方召回 → 风险评分 → 预警
  risk_predictor（主动）：早期信号 → 趋势预测 → 预防性预警

数据来源（早期信号）：
  - 供应商历史问题记录（来自 causal_knowledge）
  - 国别风险趋势（来自 country_risk_summary 时序）
  - 产品类别历史事件密度变化
  - 因果链中的新增高风险节点
"""

from datetime import datetime, timedelta
from typing import Any

from ..adapters.alerts.db_alert_publisher import DbAlertPublisher
from ..ports.alert_publisher import AlertPublisher
from .db import get_db_connection
from .stores import AlertStore, UnitOfWork

# ─────────────────────────────────────────────────────────────
# 预测引擎基类（可扩展）
# ─────────────────────────────────────────────────────────────

class BasePredictor:
    """预测引擎基类，子类可替换预测算法"""

    def predict(self, series: list[float], horizon: int = 3) -> list[float]:
        """
        Args:
            series: 历史时间序列（如每月事件数）
            horizon: 预测步数（月）

        Returns:
            预测值列表
        """
        raise NotImplementedError


class SimpleMovingAveragePredictor(BasePredictor):
    """简单移动平均预测器（轻量，无 ML 依赖）"""

    def __init__(self, window: int = 3):
        self.window = window

    def predict(self, series: list[float], horizon: int = 3) -> list[float]:
        if len(series) < self.window:
            # 数据不足，用均值
            mean = sum(series) / len(series) if series else 0.0
            return [mean] * horizon

        windowed = series[-self.window:]
        weights = list(range(1, self.window + 1))
        weighted_avg = sum(w * v for w, v in zip(weights, windowed)) / sum(weights)

        # 加入趋势修正：如果最近趋势上升，略微上调
        if len(series) >= 2 and series[-1] > series[-2]:
            trend_factor = 1 + (series[-1] - series[-2]) / (series[-2] + 1) * 0.1
        elif len(series) >= 2 and series[-1] < series[-2]:
            trend_factor = 1 - (series[-2] - series[-1]) / (series[-2] + 1) * 0.1
        else:
            trend_factor = 1.0

        return [round(weighted_avg * trend_factor, 4)] * horizon


class AnomalyDetector:
    """基于统计的历史异常检测"""

    def __init__(self, threshold_sigma: float = 2.0):
        self.threshold_sigma = threshold_sigma

    def detect(self, series: list[float]) -> list[tuple[int, float, str]]:
        """
        检测历史序列中的异常点。

        Returns:
            [(index, value, "high"|"low"), ...]
        """
        if len(series) < 3:
            return []

        mean = sum(series) / len(series)
        variance = sum((x - mean) ** 2 for x in series) / len(series)
        std = variance ** 0.5

        anomalies = []
        for i, v in enumerate(series):
            if std > 0:
                z = abs(v - mean) / std
                if z > self.threshold_sigma:
                    anomalies.append((i, v, "high" if v > mean else "low"))
        return anomalies


# ─────────────────────────────────────────────────────────────
# 核心预测逻辑
# ─────────────────────────────────────────────────────────────

class RiskPredictor:
    """
    时序风险预测器。

    支持两类预测：
    1. 国别/产品维度的风险事件密度预测（数量预测）
    2. 单个产品的风险等级趋势预测（概率预测）
    """

    def __init__(self, db_path: str | None = None,
                 predictor: BasePredictor | None = None,
                 anomaly_detector: AnomalyDetector | None = None):
        self.db_path = db_path
        self.predictor = predictor or SimpleMovingAveragePredictor(window=3)
        self.anomaly_detector = anomaly_detector or AnomalyDetector(threshold_sigma=2.0)

    # ── 时间序列构建 ─────────────────────────────────────

    def build_monthly_series(
        self,
        dimension: str,
        dimension_value: str,
        months: int = 12,
    ) -> list[dict[str, Any]]:
        """
        构建某维度的月度事件数量序列。

        Args:
            dimension: 维度字段名（country / product_category / manufacturer）
            dimension_value: 维度值（如"美国"）
            months: 历史月数

        Returns:
            [{"month": "2025-07", "count": 5, "avg_score": 4500.0}, ...]
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        start_date = (datetime.now() - timedelta(days=months * 31)).strftime("%Y-%m-01")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

        cursor.execute(f"""
            SELECT
                strftime('%Y-%m', publish_date) as month,
                COUNT(*) as event_count,
                AVG(total_score) as avg_score,
                SUM(CASE WHEN rs_level = 'S' THEN 1 ELSE 0 END) as s_count,
                SUM(CASE WHEN rs_level = 'M' THEN 1 ELSE 0 END) as m_count
            FROM risk_events
            WHERE {dimension} = ?
              AND publish_date IS NOT NULL
              AND publish_date >= ?
              AND ss_score IS NOT NULL
            GROUP BY strftime('%Y-%m', publish_date)
            ORDER BY month
        """, (dimension_value, start_date))

        rows = [dict(r) for r in cursor.fetchall()]
        # 过滤掉无法解析月份的记录（如 publish_date 不是合法日期）
        rows = [r for r in rows if r["month"] is not None]
        conn.close()

        # 填充缺失月份
        all_months = []
        if rows:
            first_month = rows[0]["month"]
            last_month = rows[-1]["month"]
            # 简单填充逻辑：如果某月缺失，count=0
            existing_months = {r["month"] for r in rows}  # noqa: F841 — 刻意用法(见 TD03)
            current = datetime.strptime(first_month, "%Y-%m")  # noqa: DTZ007 — 项目使用本地时间(naive),有意识设计
            end = datetime.strptime(last_month, "%Y-%m")  # noqa: DTZ007 — 项目使用本地时间(naive),有意识设计
            while current <= end:
                month_str = current.strftime("%Y-%m")
                existing = next((r for r in rows if r["month"] == month_str), None)
                if existing:
                    all_months.append(existing)
                else:
                    all_months.append({
                        "month": month_str,
                        "event_count": 0,
                        "avg_score": 0.0,
                        "s_count": 0,
                        "m_count": 0,
                    })
                current += timedelta(days=32)
                current = current.replace(day=1)

        return all_months

    def get_current_monthly_avg(self, dimension: str, dimension_value: str,
                                months: int = 12) -> float:
        """获取当前月均事件数"""
        series = self.build_monthly_series(dimension, dimension_value, months)
        counts = [m["event_count"] for m in series]
        return sum(counts) / len(counts) if counts else 0.0

    # ── 预测执行 ─────────────────────────────────────────

    def predict_country_risk(
        self,
        country: str,
        horizon_months: int = 6,
    ) -> dict[str, Any]:
        """
        预测某国别的风险趋势。

        Returns:
            {
                "country": str,
                "current_avg": float,
                "predictions": [{"month": "2025-10", "predicted": 5.2}, ...],
                "anomalies": [(index, value, "high"|"low"), ...],
                "risk_level": "S"|"M"|"L"|"A",
                "confidence": float,
                "early_warning": str,
            }
        """
        series_data = self.build_monthly_series("country", country, months=12)
        counts = [m["event_count"] for m in series_data]

        predictions = self.predictor.predict(counts, horizon=horizon_months)
        anomalies = self.anomaly_detector.detect(counts)

        # 预测月均
        predicted_avg = sum(predictions) / len(predictions) if predictions else 0

        # 当前月均
        current_avg = sum(counts) / len(counts) if counts else 0

        # 趋势判断
        trend = "increasing" if predicted_avg > current_avg * 1.2 else \
                "decreasing" if predicted_avg < current_avg * 0.8 else "stable"

        # 风险等级（基于预测值）
        risk_level = "S" if predicted_avg >= 8 else \
                     "M" if predicted_avg >= 4 else \
                     "L" if predicted_avg >= 2 else "A"

        # 置信度（基于历史数据量和稳定性）
        confidence = min(0.95, len(counts) / 12 * 0.8 + 0.2) if counts else 0.2

        # 早期预警
        early_warning = ""
        if trend == "increasing" and predicted_avg > current_avg * 1.5:
            early_warning = f"⚠️ 预警：该国风险事件预计上升 {((predicted_avg/current_avg-1)*100):.0f}%，建议加强检验"
        elif anomalies and any(a[2] == "high" for a in anomalies):
            early_warning = "⚠️ 异常检测：近12个月存在异常高发期，可能持续"

        # 构建月度预测
        prediction_months = []
        last_month = datetime.now()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        for p in predictions:
            last_month += timedelta(days=32)
            last_month = last_month.replace(day=1)
            prediction_months.append({
                "month": last_month.strftime("%Y-%m"),
                "predicted_events": round(p, 1),
            })

        return {
            "country": country,
            "current_monthly_avg": round(current_avg, 2),
            "predicted_monthly_avg": round(predicted_avg, 2),
            "trend": trend,
            "risk_level": risk_level,
            "confidence": round(confidence, 2),
            "prediction_months": prediction_months,
            "anomalies": [(a[0], round(a[1], 2), a[2]) for a in anomalies],
            "early_warning": early_warning,
        }

    def predict_product_risk(
        self,
        product_name: str,
        country: str,
        horizon_months: int = 6,
    ) -> dict[str, Any]:
        """预测某产品的风险趋势"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT publish_date, total_score, rs_level
            FROM risk_events
            WHERE product_name = ? AND country = ?
              AND publish_date IS NOT NULL
              AND ss_score IS NOT NULL
            ORDER BY publish_date
        """, (product_name, country))
        rows = [dict(r) for r in cursor.fetchall()]
        # 过滤掉无法解析月份的记录
        rows = [r for r in rows if isinstance(r["publish_date"], str) and len(r["publish_date"]) >= 7]
        conn.close()

        if not rows:
            return {
                "product_name": product_name,
                "country": country,
                "status": "no_data",
                "message": "无历史数据，无法预测",
            }

        # 构建月度序列
        monthly: dict[str, list[float]] = {}
        for r in rows:
            month = r["publish_date"][:7]  # "2025-07"
            if month not in monthly:
                monthly[month] = []
            monthly[month].append(r["total_score"])

        series_data = sorted(monthly.items())
        avg_scores = [sum(scores) / len(scores) for _, scores in series_data]
        predictions = self.predictor.predict(avg_scores, horizon=horizon_months)

        predicted_avg = sum(predictions) / len(predictions)
        current_avg = sum(avg_scores) / len(avg_scores) if avg_scores else 0

        return {
            "product_name": product_name,
            "country": country,
            "current_avg_score": round(current_avg, 2),
            "predicted_avg_score": round(predicted_avg, 2),
            "trend": "increasing" if predicted_avg > current_avg * 1.2 else \
                     "decreasing" if predicted_avg < current_avg * 0.8 else "stable",
            "risk_level": "S" if predicted_avg >= 8000 else \
                          "M" if predicted_avg >= 3000 else \
                          "L" if predicted_avg >= 1000 else "A",
            "prediction_months": [
                {"month": m, "predicted_score": round(p, 0)}
                for m, p in zip(
                    [(datetime.now() + timedelta(days=32 * i)).strftime("%Y-%m")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
                     for i in range(1, horizon_months + 1)],
                    predictions
                )
            ],
        }

    # ── 全维度扫描 ─────────────────────────────────────

    def scan_early_warnings(self, horizon_months: int = 6) -> dict[str, Any]:
        """
        扫描所有维度的早期预警信号。
        这替代了 alert_engine 的纯阈值规则，实现预测性预警。
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # 扫描高风险国别
        cursor.execute("SELECT DISTINCT country FROM risk_events WHERE country IS NOT NULL AND country != 'unknown'")
        countries = [r["country"] for r in cursor.fetchall()]

        # 扫描高风险产品类别
        cursor.execute("SELECT DISTINCT product_category FROM risk_events WHERE product_category IS NOT NULL")
        categories = [r["product_category"] for r in cursor.fetchall()]

        conn.close()

        country_warnings = []
        for country in countries:
            pred = self.predict_country_risk(country, horizon_months)
            if pred["trend"] == "increasing" and pred["predicted_monthly_avg"] > pred["current_monthly_avg"] * 1.3:
                country_warnings.append(pred)

        category_warnings = []
        for cat in categories:
            series_data = self.build_monthly_series("product_category", cat, months=12)
            counts = [m["event_count"] for m in series_data]
            predictions = self.predictor.predict(counts, horizon=horizon_months)
            predicted_avg = sum(predictions) / len(predictions)
            current_avg = sum(counts) / len(counts) if counts else 0
            if predicted_avg > current_avg * 1.5:
                category_warnings.append({
                    "category": cat,
                    "current_avg": round(current_avg, 2),
                    "predicted_avg": round(predicted_avg, 2),
                    "trend": "increasing",
                    "confidence": round(min(0.9, len(counts) / 12 * 0.8 + 0.1), 2),
                })

        return {
            "scan_time": datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            "horizon_months": horizon_months,
            "country_warnings": sorted(country_warnings, key=lambda x: -x["predicted_monthly_avg"]),
            "category_warnings": sorted(category_warnings, key=lambda x: -x["predicted_avg"]),
            "total_warnings": len(country_warnings) + len(category_warnings),
        }

    # ── 预测性预警写入 ─────────────────────────────────

    def _publish_warnings(
        self,
        warnings: dict[str, Any],
        publisher: AlertPublisher,
    ) -> int:
        """通过 publisher 批量发布国别/类别预警。"""
        import uuid

        created = 0
        for pred in warnings["country_warnings"]:
            if publisher.publish(
                {
                    "alert_id": str(uuid.uuid4()),
                    "rule_id": "predictive_country",
                    "rule_name": "预测性国别风险预警",
                    "object_type": "country",
                    "object_value": pred["country"],
                    "severity": "medium",
                    "triggered_value": f"预测月均{pred['predicted_monthly_avg']:.1f}起（当前{pred['current_monthly_avg']:.1f}）",
                    "description": pred["early_warning"]
                    or "预测未来6个月风险上升趋势，建议重点关注",
                }
            ):
                created += 1

        for pred in warnings["category_warnings"]:
            if publisher.publish(
                {
                    "alert_id": str(uuid.uuid4()),
                    "rule_id": "predictive_category",
                    "rule_name": "预测性产品类别风险预警",
                    "object_type": "product_category",
                    "object_value": pred["category"],
                    "severity": "medium",
                    "triggered_value": f"预测月均{pred['predicted_avg']:.1f}起（当前{pred['current_avg']:.1f}起）",
                    "description": f"产品类别'{pred['category']}'风险事件预计大幅上升，建议加强检验",
                }
            ):
                created += 1

        return created

    def write_predictive_alerts(
        self,
        warnings: dict[str, Any] | None = None,
        publisher: AlertPublisher | None = None,
        uow: UnitOfWork | None = None,
    ) -> dict[str, Any]:
        """
        执行扫描，将早期预警写入 alert_records 表。
        这是替代 alert_engine 纯阈值规则的新一代预警方式。

        Phase 3C 重构：
        - 不再直接执行 SQL，而是通过 AlertPublisher 发布预警。
        - 支持注入 publisher/uow 进行测试与事务复用。
        """
        if warnings is None:
            warnings = self.scan_early_warnings(horizon_months=6)

        if warnings["total_warnings"] == 0:
            return {
                "status": "success",
                "records_created": 0,
                "message": "无早期预警信号",
            }

        if publisher is None:
            if uow is not None:
                publisher = DbAlertPublisher(AlertStore(uow))
                created = self._publish_warnings(warnings, publisher)
            else:
                with UnitOfWork(self.db_path) as uow_inner:
                    publisher = DbAlertPublisher(AlertStore(uow_inner))
                    created = self._publish_warnings(warnings, publisher)
        else:
            created = self._publish_warnings(warnings, publisher)

        return {
            "status": "success",
            "records_created": created,
            "total_warnings": warnings["total_warnings"],
            "message": f"写入 {created} 条预测性预警",
        }

    # ── 主入口 ─────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """模块主入口：执行预测扫描和预警写入"""
        warnings = self.scan_early_warnings(horizon_months=6)
        result = self.write_predictive_alerts(warnings)

        return {
            "module": "risk_predictor",
            "status": "success",
            "warnings_found": warnings["total_warnings"],
            "alerts_created": result["records_created"],
            "country_warnings": len(warnings["country_warnings"]),
            "category_warnings": len(warnings["category_warnings"]),
            "message": result["message"],
        }


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from .db import init_db
    init_db()

    predictor = RiskPredictor()

    # 测试国别预测
    result = predictor.predict_country_risk("美国", horizon_months=6)
    print("美国风险预测:")
    print(f"  当前月均: {result['current_monthly_avg']}")
    print(f"  预测月均: {result['predicted_monthly_avg']}")
    print(f"  趋势: {result['trend']}")
    print(f"  风险等级: {result['risk_level']}")
    print(f"  早期预警: {result['early_warning']}")

    # 全维度扫描
    print("\n早期预警扫描:")
    warnings = predictor.scan_early_warnings(horizon_months=6)
    print(f"  国别预警: {len(warnings['country_warnings'])}")
    print(f"  类别预警: {len(warnings['category_warnings'])}")

    # 执行预测性预警
    print("\n写入预测性预警:")
    result = predictor.write_predictive_alerts()
    print(f"  结果: {result}")
