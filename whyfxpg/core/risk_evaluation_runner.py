"""风险评分编排模块 (Phase 3A seam / Phase 4D 类型化)。

设计决策：
- RiskEvaluationRunner 负责工作流：读取待评分事件 → 获取历史统计 → 调用 RiskScorer
  → 更新数据库 → 可选 LLM 推理 → 重建汇总表。
- 所有数据访问通过 RiskEventStore / SummaryStore / UnitOfWork。
- 因果增强通过 CausalPort 注入，默认使用 DbCausalAdapter；测试可替换为 InMemory。
- LLM 推理通过 LLMService 注入，与 scorer 解耦。
- 本模块持有 ConfigLoader 解析出的类型化 RiskModelConfig，避免裸 dict 访问。
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..adapters.causal.db_causal_adapter import DbCausalAdapter
from ..ports.causal_port import CausalPort
from ..services.llm_service import LLMService
from .config_loader import DEFAULT_CONFIG_DIR, ConfigLoader
from .config_version import ConfigVersionManager
from .risk_scorer import RiskScorer
from .stores import RiskEventStore, SummaryStore, UnitOfWork


class RiskEvaluationRunner:
    """风险评分工作流编排器。

    Interface（对外 seams）：
        __init__(config_dir=None, db_path=None, scorer=None,
                 llm_service=None, causal_port=None)
        run(uow=None) -> dict
        evaluate_event(event, conn) -> dict
    """

    def __init__(
        self,
        config_dir: str | None = None,
        db_path: str | None = None,
        scorer: RiskScorer | None = None,
        llm_service: LLMService | None = None,
        causal_port: CausalPort | None = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.db_path = db_path
        self.loader = ConfigLoader(str(self.config_dir))
        self.model_cfg = self.loader.typed_risk_model
        self.scorer = scorer or RiskScorer(self.model_cfg)
        self._llm_service = llm_service
        self._causal_port = causal_port

    @property
    def llm_service(self) -> LLMService:
        if self._llm_service is None:
            self._llm_service = LLMService()
        return self._llm_service

    @llm_service.setter
    def llm_service(self, value: LLMService | None) -> None:
        self._llm_service = value

    def _get_causal(self, uow: UnitOfWork) -> CausalPort:
        if self._causal_port is not None:
            return self._causal_port
        return DbCausalAdapter(uow)

    def _current_config_version(self, conn: sqlite3.Connection) -> str:
        manager = ConfigVersionManager.from_connection(conn, str(self.config_dir))
        latest = manager.get_latest_db_version()
        return latest["version_id"] if latest else "1.0"

    def _historical_counts(
        self,
        event: dict[str, Any],
        risk_store: RiskEventStore,
    ) -> dict[str, int]:
        since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        country_history = risk_store.count_history(
            since,
            event.get("country", "unknown"),
            event.get("manufacturer", "unknown"),
            event.get("product_category", "普通机电"),
            event.get("hazard_type", "组合危险"),
        )
        product_history = risk_store.count_history_by_product(
            since,
            event.get("product_category", "普通机电"),
            event.get("hazard_type", "组合危险"),
        )
        return {
            "country_history_count": country_history,
            "product_history_count": product_history,
        }

    def evaluate_event(
        self,
        event: dict[str, Any],
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        """评估单个事件（兼容旧签名，复用 conn 创建临时 Store）。"""
        uow = UnitOfWork.from_connection(conn)
        risk_store = RiskEventStore(uow)
        causal = self._get_causal(uow)
        counts = self._historical_counts(event, risk_store)
        result = self.scorer.score(event, counts, causal.factor(event))
        return result.__dict__

    def add_risk_reasoning(
        self,
        event: dict[str, Any],
        conn: sqlite3.Connection,
    ) -> str:
        """为 S/M 级事件生成 LLM 风险推理并写入 hazard_desc。"""
        if event.get("rs_level") not in ("S", "M"):
            return ""
        reasoning = self.llm_service.risk_reasoning(event)
        if not reasoning:
            return ""
        RiskEventStore(UnitOfWork.from_connection(conn)).append_risk_reasoning(
            event["event_id"], reasoning
        )
        return reasoning

    def _run_with_uow(self, uow: UnitOfWork) -> dict[str, Any]:
        risk_store = RiskEventStore(uow)
        events = risk_store.fetch_pending()
        if not events:
            return {
                "module": "risk_model",
                "status": "success",
                "records_processed": 0,
                "records_created": 0,
                "errors": [],
                "message": "没有待评分事件",
            }

        summary_store = SummaryStore(uow)
        causal = self._get_causal(uow)
        config_version = self._current_config_version(uow.connection)
        model_version = self.model_cfg.version
        errors: list[str] = []
        evaluated = 0

        for event in events:
            try:
                counts = self._historical_counts(event, risk_store)
                scoring_result = self.scorer.score(event, counts, causal.factor(event))
                result = scoring_result.__dict__
                risk_store.update_scores(
                    event["event_id"], result, config_version, model_version
                )
                evaluated += 1

                # 动态评分刷新：新信号触发相关历史事件重算
                scored_event = {**event, **result}
                rescored_count = risk_store.rescore_related(scored_event)
                if rescored_count > 0:
                    errors.append(f"{event['event_id']}[重算]: 触发 {rescored_count} 条相关事件")

                if result["rs_level"] in ("S", "M"):
                    try:
                        scored_event = {**event, **result}
                        self.add_risk_reasoning(scored_event, uow.connection)
                    except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                        errors.append(f"{event['event_id']}[推理]: {e!s}")
            except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                errors.append(f"{event['event_id']}: {e!s}")

        summary_store.rebuild_summaries(config_version, model_version)

        return {
            "module": "risk_model",
            "status": "success" if not errors else "partial",
            "records_processed": len(events),
            "records_created": evaluated,
            "errors": errors,
            "message": f"评分 {evaluated} 条事件，更新汇总表",
        }

    def run(self, uow: UnitOfWork | None = None) -> dict[str, Any]:
        """模块主入口。调用方提供 UoW 则复用，否则自行创建并提交。"""
        if uow is not None:
            return self._run_with_uow(uow)
        with UnitOfWork(self.db_path) as uow_ctx:
            return self._run_with_uow(uow_ctx)
