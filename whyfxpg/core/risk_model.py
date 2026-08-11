"""
风险评分模块 (M4) — Phase 3A 兼容性门面。

设计决策：
- 本模块已拆分为两个新 seam：
  - RiskScorer       (whyfxpg/core/risk_scorer.py)：纯评分策略，无 DB 依赖。
  - RiskEvaluationRunner (whyfxpg/core/risk_evaluation_runner.py)：工作流编排。
- RiskModel 保留为旧代码的兼容性门面，所有行为委托给上述模块。
- 新增代码应直接使用 RiskScorer / RiskEvaluationRunner；RiskModel 仅在旧入口
  （main.py、既有测试）中暂时保留。

依据：
- 避免 main.py 与既有测试在本次重构中大面积改动。
- 门面模式让旧调用点无感迁移，同时把核心逻辑下放到可独立测试的 deep module。
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..adapters.causal.db_causal_adapter import DbCausalAdapter
from ..ports.causal_port import CausalPort
from ..services.llm_service import LLMService
from .config_loader import DEFAULT_CONFIG_DIR, ConfigLoader
from .config_version import ConfigVersionManager
from .risk_evaluation_runner import RiskEvaluationRunner
from .risk_scorer import RiskScorer
from .stores import SummaryStore, UnitOfWork

if TYPE_CHECKING:
    from whyfxpg.config.pydantic_models import RiskModelConfig


class RiskModel:
    """风险评分模型（兼容性门面）。"""

    def __init__(
        self,
        config_dir: str | None = None,
        db_path: str | None = None,
        llm_service: LLMService | None = None,
        causal_port: CausalPort | None = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.db_path = db_path
        self._llm_service = llm_service
        self._causal_port = causal_port
        self._loader = ConfigLoader(str(self.config_dir))
        self._scorer: RiskScorer | None = None
        self._runner: RiskEvaluationRunner | None = None

    @property
    def model_cfg(self) -> "RiskModelConfig":
        return self._loader.typed_risk_model

    @property
    def llm_service(self) -> LLMService:
        if self._llm_service is None:
            self._llm_service = LLMService()
        return self._llm_service

    @property
    def causal(self) -> Any:
        """懒加载因果知识图谱（外部使用，不强制复用连接）。"""
        if self._causal_port is not None:
            return self._causal_port
        return DbCausalAdapter(UnitOfWork(self.db_path))

    def _scorer_instance(self) -> RiskScorer:
        if self._scorer is None:
            self._scorer = RiskScorer(self.model_cfg)
        return self._scorer

    def _runner_instance(self) -> RiskEvaluationRunner:
        if self._runner is None:
            self._runner = RiskEvaluationRunner(
                config_dir=str(self.config_dir),
                db_path=self.db_path,
                scorer=self._scorer_instance(),
                llm_service=self._llm_service,
                causal_port=self._causal_port,
            )
        return self._runner

    def llm_risk_reasoning(self, event: dict[str, Any]) -> str:
        """为风险事件生成可解释性推理说明（300 字以内）。"""
        try:
            reasoning = self.llm_service.risk_reasoning(event)
            return reasoning[:300] if reasoning else ""
        except Exception:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return ""

    def severity_to_score(self, severity_level: str) -> int:
        return self._scorer_instance().severity_to_score(severity_level)

    def probability_to_score(self, event: dict[str, Any], risk_store: Any) -> int:
        """概率等级转分数（兼容旧签名；依赖 RiskEventStore）。"""
        from datetime import datetime, timedelta


        since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        count = risk_store.count_history(
            since,
            event.get("country", "unknown"),
            event.get("manufacturer", "unknown"),
            event.get("product_category", "普通机电"),
            event.get("hazard_type", "组合危险"),
        )
        return self._scorer_instance().probability_to_score(event, count)

    def get_country_factor(self, country: str) -> float:
        return self._scorer_instance().country_factor(country)

    def get_product_factor(self, category: str) -> float:
        return self._scorer_instance().product_factor(category)

    def get_history_factor(self, event_count_12m: int) -> float:
        return self._scorer_instance().history_factor(event_count_12m)

    def get_evidence_factor(self, source_id: str) -> float:
        return self._scorer_instance().evidence_factor(source_id)

    def calculate_total_score(
        self,
        ss: int,
        ps: int,
        country_factor: float,
        product_factor: float,
        history_factor: float,
        evidence_factor: float,
    ) -> float:
        return self._scorer_instance().calculate_total_score(
            ss, ps, country_factor, product_factor, history_factor, evidence_factor
        )

    def map_to_risk_level(self, total_score: float) -> str:
        return self._scorer_instance().map_to_risk_level(total_score)

    def get_current_config_version(
        self, conn: sqlite3.Connection | None = None
    ) -> str:
        manager = ConfigVersionManager(str(self.config_dir), self.db_path, conn=conn)
        latest = manager.get_latest_db_version()
        return latest["version_id"] if latest else "1.0"

    def evaluate_event(
        self, event: dict[str, Any], conn: sqlite3.Connection
    ) -> dict[str, Any]:
        """评估单个事件（兼容旧签名）。"""
        return self._runner_instance().evaluate_event(event, conn)

    def add_risk_reasoning(
        self, event: dict[str, Any], conn: sqlite3.Connection | None = None
    ) -> str:
        """为已评分事件生成 LLM 风险推理说明并更新数据库。"""
        if conn is not None:
            return self._runner_instance().add_risk_reasoning(event, conn)

        if event.get("rs_level") not in ("S", "M"):
            return ""
        reasoning = self.llm_risk_reasoning(event)
        if not reasoning:
            return ""
        with UnitOfWork(self.db_path) as uow:
            from .stores import RiskEventStore

            RiskEventStore(uow).append_risk_reasoning(event["event_id"], reasoning)
        return reasoning

    def update_summaries(
        self, summary_store: SummaryStore, config_version: str | None = None
    ) -> None:
        if config_version is None:
            config_version = self.get_current_config_version()
        model_version = self.model_cfg.version
        summary_store.rebuild_summaries(config_version, model_version)

    def run(self, uow: UnitOfWork | None = None) -> dict[str, Any]:
        """模块主入口。"""
        return self._runner_instance().run(uow)


if __name__ == "__main__":
    from .db import init_db

    init_db()
    model = RiskModel()
    print(model.run())
