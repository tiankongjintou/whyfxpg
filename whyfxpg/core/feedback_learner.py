"""
反馈学习模块（闭环核心）

功能：
- 读取 manual_reviews 表中的人工复核记录
- 分析修正历史，自动调整风险模型的系数参数
- 将学习结果写回 risk_model.yaml 或 causal_knowledge 图谱
- 形成"bot评分 → human修正 → bot学习 → 更准bot评分"的闭环

学习策略：
1. 国别系数学习：若某国别连续N次被human向上修正，调整其country_factor
2. 产品系数学习：若某产品类别持续被修正，调整product_factor
3. 严重度量表学习：统计human给出的severity_level与模型推断的差异，修正severity量表
4. 因果权重学习：若某制造商被持续降低风险，说明其实际风险低于模型预期，微调其节点 risk_score

飞轮数据流：
  risk_model 评分 → alert_engine 预警 → WebUI 人工复核界面 → manual_reviews 表
      ↑                                                                          ↓
      └── feedback_learner 分析修正 ←─────────────────────────────────────────────┘
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .causal_knowledge import CausalKnowledge
from .db import get_db_connection


class FeedbackLearner:
    """
    反馈学习器：分析人工修正历史，自动调整模型系数。

    学习触发条件（保守策略，防止单次修正造成剧烈波动）：
    - 同一维度（国别/产品类别）需积累 >= MIN_REVIEWS_FOR_LEARNING 条修正
    - 修正方向一致性 >= 70%（超过半数修正朝同一方向）
    - 修正幅度需超过 CLIPPING_THRESHOLD（防止微调震荡）
    """

    # 学习触发阈值
    MIN_REVIEWS_FOR_LEARNING = 5      # 至少5条修正才触发学习
    CONSISTENCY_THRESHOLD = 0.70      # 修正一致性阈值
    CLIPPING_THRESHOLD = 0.05        # 修正幅度阈值（5%以上才真正调整）
    LEARNING_RATE = 0.20             # 每次学习调整20%的差距

    def __init__(self, db_path: str | None = None, config_dir: str | None = None):
        self.db_path = db_path
        self.config_dir = Path(config_dir) if config_dir else None
        self._causal: CausalKnowledge | None = None

    @property
    def causal(self) -> CausalKnowledge:
        if self._causal is None:
            self._causal = CausalKnowledge(self.db_path)
        return self._causal

    # ── 数据读取 ──────────────────────────────────────────

    def get_recent_reviews(self, days: int = 90, limit: int = 200) -> list[dict[str, Any]]:
        """读取近N天的人工修正记录"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        cursor.execute("""
            SELECT r.*, e.product_name, e.country, e.manufacturer,
                   e.product_category, e.severity_level as model_severity,
                   e.rs_level as model_rs
            FROM manual_reviews r
            JOIN risk_events e ON r.event_id = e.event_id
            WHERE r.reviewed_at >= ?
            ORDER BY r.reviewed_at DESC
            LIMIT ?
        """, (since, limit))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_country_corrections(self, reviews: list[dict]) -> dict[str, list[dict]]:
        """按国别分组修正记录"""
        grouped: dict[str, list[dict]] = {}
        for r in reviews:
            country = r.get("country", "unknown")
            if country and country != "unknown":
                if country not in grouped:
                    grouped[country] = []
                grouped[country].append(r)
        return grouped

    def get_product_corrections(self, reviews: list[dict]) -> dict[str, list[dict]]:
        """按产品类别分组修正记录"""
        grouped: dict[str, list[dict]] = {}
        for r in reviews:
            cat = r.get("product_category", "普通机电")
            if cat:
                if cat not in grouped:
                    grouped[cat] = []
                grouped[cat].append(r)
        return grouped

    def get_manufacturer_corrections(self, reviews: list[dict]) -> dict[str, list[dict]]:
        """按制造商分组修正记录"""
        grouped: dict[str, list[dict]] = {}
        for r in reviews:
            mfr = r.get("manufacturer", "unknown")
            if mfr and mfr != "unknown":
                if mfr not in grouped:
                    grouped[mfr] = []
                grouped[mfr].append(r)
        return grouped

    # ── 学习分析 ──────────────────────────────────────────

    def analyze_country_learning(self, grouped: dict[str, list[dict]]) -> list[dict[str, Any]]:
        """
        分析国别系数学习需求。
        规则：若human持续将某国别事件向下修正（降低风险），说明该国实际风险被高估。
        """
        learnings = []
        for country, reviews in grouped.items():
            if len(reviews) < self.MIN_REVIEWS_FOR_LEARNING:
                continue

            # 统计 rs_level 修正方向
            upgrades = sum(1 for r in reviews if r.get("adjusted_rs") and
                           self._rs_to_score(r.get("adjusted_rs", "A")) <
                           self._rs_to_score(r.get("model_rs", "A")))
            consistency = upgrades / len(reviews)

            if consistency >= self.CONSISTENCY_THRESHOLD:
                # 计算平均修正幅度（以 severity 为代理）
                adjustments = []
                for r in reviews:
                    orig = r.get("original_ss", 50)
                    adj = r.get("adjusted_ss", orig)
                    adjustments.append((adj - orig) / orig if orig else 0)

                avg_adjustment = sum(adjustments) / len(adjustments)
                if abs(avg_adjustment) >= self.CLIPPING_THRESHOLD:
                    new_factor_delta = -avg_adjustment * self.LEARNING_RATE
                    learnings.append({
                        "target": "country",
                        "name": country,
                        "direction": "downgrade",
                        "current_adjustment": avg_adjustment,
                        "suggested_factor_delta": round(new_factor_delta, 4),
                        "review_count": len(reviews),
                        "consistency": round(consistency, 2),
                    })

        return learnings

    def analyze_product_learning(self, grouped: dict[str, list[dict]]) -> list[dict[str, Any]]:
        """分析产品类别系数学习需求"""
        learnings = []
        for cat, reviews in grouped.items():
            if len(reviews) < self.MIN_REVIEWS_FOR_LEARNING:
                continue

            upgrades = sum(1 for r in reviews if r.get("adjusted_rs") and
                           self._rs_to_score(r.get("adjusted_rs", "A")) <
                           self._rs_to_score(r.get("model_rs", "A")))
            consistency = upgrades / len(reviews)

            if consistency >= self.CONSISTENCY_THRESHOLD:
                adjustments = [(r.get("adjusted_ss", 50) - r.get("original_ss", 50)) / max(r.get("original_ss", 1), 1)
                               for r in reviews]
                avg_adj = sum(adjustments) / len(adjustments)
                if abs(avg_adj) >= self.CLIPPING_THRESHOLD:
                    learnings.append({
                        "target": "product_category",
                        "name": cat,
                        "direction": "downgrade" if avg_adj < 0 else "upgrade",
                        "current_adjustment": avg_adj,
                        "suggested_factor_delta": round(-avg_adj * self.LEARNING_RATE, 4),
                        "review_count": len(reviews),
                        "consistency": round(consistency, 2),
                    })
        return learnings

    def analyze_manufacturer_learning(self, grouped: dict[str, list[dict]]) -> list[dict[str, Any]]:
        """
        分析制造商因果节点学习。
        若某制造商持续被向下修正，说明其实际风险低于 causal_knowledge 中预设值，
        需调低其节点的 risk_score。
        """
        learnings = []
        for mfr, reviews in grouped.items():
            if len(reviews) < self.MIN_REVIEWS_FOR_LEARNING:
                continue

            # 检查 rs_level 是否被持续降低
            downgrades = sum(1 for r in reviews if r.get("adjusted_rs") and
                             self._rs_to_score(r.get("adjusted_rs", "A")) <
                             self._rs_to_score(r.get("model_rs", "A")))
            consistency = downgrades / len(reviews)

            if consistency >= self.CONSISTENCY_THRESHOLD:
                # 计算该制造商的评分调整幅度
                adjustments = [(r.get("adjusted_ss", 50) - r.get("original_ss", 50))
                               for r in reviews]
                avg_adj = sum(adjustments) / len(adjustments)
                if abs(avg_adj) >= self.CLIPPING_THRESHOLD:
                    # 换算为 risk_score 调整（risk_score 范围 [0, 1]）
                    score_delta = -avg_adj / 100 * self.LEARNING_RATE  # ss_score 约50-100范围
                    learnings.append({
                        "target": "manufacturer",
                        "name": mfr,
                        "direction": "downgrade",
                        "avg_severity_adjustment": round(avg_adj, 3),
                        "suggested_risk_score_delta": round(score_delta, 4),
                        "review_count": len(reviews),
                        "consistency": round(consistency, 2),
                    })
        return learnings

    @staticmethod
    def _rs_to_score(level: str) -> int:
        mapping = {"S": 4, "M": 3, "L": 2, "A": 1}
        return mapping.get(level, 2)

    # ── 应用学习结果 ──────────────────────────────────────

    def apply_country_learning(self, learnings: list[dict[str, Any]],
                               yaml_config: dict[str, Any]) -> list[dict[str, Any]]:
        """将国别学习结果写回 risk_model.yaml 配置"""
        changes = []
        country_factors = yaml_config.get("country_factors", {})

        for lg in learnings:
            country = lg["name"]
            current = country_factors.get(country, 1.0)
            delta = lg["suggested_factor_delta"]
            new_val = max(0.5, min(2.0, current + delta))
            country_factors[country] = round(new_val, 3)
            changes.append({
                "target": country,
                "old": current,
                "new": new_val,
                "delta": round(delta, 4),
                "reason": f"{lg['review_count']}条修正，{lg['consistency']*100:.0f}%一致性",
            })

        yaml_config["country_factors"] = country_factors
        return changes

    def apply_product_learning(self, learnings: list[dict[str, Any]],
                               yaml_config: dict[str, Any]) -> list[dict[str, Any]]:
        """将产品类别学习结果写回配置"""
        changes = []
        product_factors = yaml_config.get("product_factors", {})

        for lg in learnings:
            cat = lg["name"]
            current = product_factors.get(cat, 1.0)
            delta = lg["suggested_factor_delta"]
            new_val = max(0.5, min(2.0, current + delta))
            product_factors[cat] = round(new_val, 3)
            changes.append({
                "target": cat,
                "old": current,
                "new": new_val,
                "delta": round(delta, 4),
                "reason": f"{lg['review_count']}条修正，{lg['consistency']*100:.0f}%一致性",
            })

        yaml_config["product_factors"] = product_factors
        return changes

    def apply_manufacturer_learning(self, learnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将制造商学习结果写回因果知识图谱"""
        changes = []
        for lg in learnings:
            mfr_node_id = f"manufacturer:{lg['name']}"
            current_node = self.causal.get_node(mfr_node_id)
            if current_node:
                current_score = current_node.get("risk_score", 1.0)
                delta = lg["suggested_risk_score_delta"]
                new_score = max(0.1, min(1.0, current_score + delta))
                self.causal.add_node(
                    "manufacturer",
                    lg["name"],
                    risk_score=round(new_score, 3),
                    properties={"learned_from_feedback": True,
                                "review_count": lg["review_count"],
                                "consistency": lg["consistency"]},
                    source="feedback_learning"
                )
                changes.append({
                    "target": mfr_node_id,
                    "old_risk_score": current_score,
                    "new_risk_score": round(new_score, 3),
                    "delta": round(delta, 4),
                    "reason": f"{lg['review_count']}条修正，{lg['consistency']*100:.0f}%一致性",
                })
        return changes

    # ── 主学习流程 ───────────────────────────────────────

    def learn(self, yaml_config: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        执行完整反馈学习流程。

        Args:
            yaml_config: risk_model.yaml 配置字典（若传入则直接修改后返回）
        """
        if yaml_config is None:
            from .config_loader import DEFAULT_CONFIG_DIR, ConfigLoader
            yaml_config = ConfigLoader(str(DEFAULT_CONFIG_DIR)).risk_model

        reviews = self.get_recent_reviews(days=90)
        if not reviews:
            return {
                "status": "skipped",
                "message": "近90天无人工复核记录，跳过学习",
            }

        summary: dict[str, Any] = {
            "total_reviews": len(reviews),
            "country_learnings": [],
            "product_learnings": [],
            "manufacturer_learnings": [],
        }

        # 国别学习
        country_grouped = self.get_country_corrections(reviews)
        country_lg = self.analyze_country_learning(country_grouped)
        if country_lg:
            summary["country_learnings"] = self.apply_country_learning(country_lg, yaml_config)

        # 产品类别学习
        product_grouped = self.get_product_corrections(reviews)
        product_lg = self.analyze_product_learning(product_grouped)
        if product_lg:
            summary["product_learnings"] = self.apply_product_learning(product_lg, yaml_config)

        # 制造商因果学习
        mfr_grouped = self.get_manufacturer_corrections(reviews)
        mfr_lg = self.analyze_manufacturer_learning(mfr_grouped)
        if mfr_lg:
            summary["manufacturer_learnings"] = self.apply_manufacturer_learning(mfr_lg)

        applied = (
            len(summary["country_learnings"]) +
            len(summary["product_learnings"]) +
            len(summary["manufacturer_learnings"])
        )
        summary["status"] = "success" if applied > 0 else "no_learning_triggered"
        summary["message"] = f"分析{len(reviews)}条修正，触发{applied}项学习调整"
        summary["yaml_config"] = yaml_config

        return summary

    def get_learning_report(self, days: int = 90) -> str:
        """生成反馈学习报告（供人工审核）"""
        reviews = self.get_recent_reviews(days=days)
        if not reviews:
            return f"近{days}天无人工复核记录，无学习报告。"

        # 按国别统计
        country_stats = {}
        for r in reviews:
            c = r.get("country", "unknown")
            if c not in country_stats:
                country_stats[c] = {"total": 0, "downgrades": 0}
            country_stats[c]["total"] += 1
            if r.get("adjusted_rs") and self._rs_to_score(r.get("adjusted_rs", "A")) < self._rs_to_score(r.get("model_rs", "A")):
                country_stats[c]["downgrades"] += 1

        lines = [
            f"=== 反馈学习报告（近{days}天）===",
            f"复核记录总数：{len(reviews)}",
            "",
            "国别修正统计：",
        ]
        for country, stat in sorted(country_stats.items(), key=lambda x: -x[1]["total"]):
            pct = stat["downgrades"] / stat["total"] * 100 if stat["total"] > 0 else 0
            flag = " ⚠️" if pct >= 50 and stat["total"] >= 3 else ""
            lines.append(f"  {country}: {stat['total']}条修正，{pct:.0f}%降级{flag}")

        if reviews:
            recent = reviews[:5]
            lines.append("")
            lines.append("最近修正记录：")
            for r in recent:
                lines.append(
                    f"  {r.get('product_name','?')} | "
                    f"原{ r.get('model_rs','?')}→现{r.get('adjusted_rs','?')} | "
                    f"原因：{str(r.get('reason',''))[:30]}"
                )

        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from .db import init_db

    init_db()
    learner = FeedbackLearner()

    print("反馈学习报告：")
    print(learner.get_learning_report())

    print("\n执行学习：")
    result = learner.learn()
    print(json.dumps({k: v for k, v in result.items() if k != "yaml_config"}, ensure_ascii=False, indent=2))
