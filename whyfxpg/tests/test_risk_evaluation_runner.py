"""RiskEvaluationRunner 编排层测试。

测试 seam：RiskEvaluationRunner.run(uow=None) 的完整工作流，
包括读取待评分事件、调用 RiskScorer、写入 risk_events、生成汇总表。
所有测试在临时 SQLite 数据库上运行，不依赖外部 LLM 或因果服务。
"""

from datetime import datetime
from typing import Any

from whyfxpg.core.db import get_db_connection
from whyfxpg.core.risk_evaluation_runner import RiskEvaluationRunner
from whyfxpg.core.stores import UnitOfWork
from whyfxpg.ports.causal_port import CausalPort
from whyfxpg.ports.llm_port import LLMPort
from whyfxpg.services.llm_service import LLMService


def _insert_pending_event(
    db_path: str,
    event_id: str = "e1",
    severity_level: str = "中等",
    country: str = "德国",
    product_category: str = "普通机电",
    hazard_type: str = "电气危险",
    source_id: str = "test_api",
) -> None:
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO risk_events (
            event_id, page_id, source_id, source_url, publish_date, title,
            product_name, brand, model, hs_code, product_category, country,
            manufacturer, hazard_type, hazard_desc, severity_level, ss_score,
            probability_level, ps_score, country_factor, product_factor,
            history_factor, evidence_factor, total_score, rs_level, standards,
            original_text, extracted_at, evaluated_at, config_version, model_version,
            extraction_confidence, review_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, "p1", source_id, "https://example.com/1", "2025-03-05", "title",
            "产品A", "品牌A", "M1", "1234", product_category, country,
            "MfrA", hazard_type, "电击", severity_level, None,
            "", None, None, None,
            None, None, None, None, "",
            "text", datetime.now().isoformat(), None, "", "",  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            0.5, "auto",
        ),
    )
    conn.commit()
    conn.close()


class FixedLLMPort(LLMPort):
    """总是返回固定文本的 LLM port，用于验证推理链路是否被调用。"""

    def __init__(self, text: str = "测试风险推理文本"):
        self._text = text

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = 0.3,
        max_tokens: int | None = 1000,
        **kwargs: Any,
    ) -> str:
        return self._text


def test_run_scores_pending_event_and_updates_summaries(
    initialized_db: str, temp_config_dir: str
) -> None:
    _insert_pending_event(initialized_db)

    runner = RiskEvaluationRunner(config_dir=temp_config_dir, db_path=initialized_db)
    result = runner.run()

    assert result["status"] == "success"
    assert result["records_processed"] == 1
    assert result["records_created"] == 1

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM product_risk_summary")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM country_risk_summary")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM enterprise_risk_summary")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_run_with_no_pending_events_returns_empty_result(
    initialized_db: str, temp_config_dir: str
) -> None:
    runner = RiskEvaluationRunner(config_dir=temp_config_dir, db_path=initialized_db)
    result = runner.run()

    assert result["status"] == "success"
    assert result["records_processed"] == 0
    assert result["records_created"] == 0
    assert "没有待评分事件" in result["message"]


def test_run_reuses_uow_connection(initialized_db: str, temp_config_dir: str) -> None:
    """Runner 应能复用调用方传入的 UnitOfWork，不自行开启新连接。"""
    import whyfxpg.core.db as db_module

    _insert_pending_event(initialized_db)
    original_get_db_connection = db_module.get_db_connection

    def raising_connection(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("不应在已提供 UoW 时开启新连接")

    db_module.get_db_connection = raising_connection
    try:
        with UnitOfWork(initialized_db) as uow:
            runner = RiskEvaluationRunner(config_dir=temp_config_dir)
            result = runner.run(uow)
            assert result["records_created"] == 1
    finally:
        db_module.get_db_connection = original_get_db_connection


def test_run_uses_injected_causal_port(
    initialized_db: str, temp_config_dir: str
) -> None:
    """Runner 应通过 CausalPort seam 注入因果因子，而不是硬编码数据库实现。"""

    class HighRiskCausalAdapter(CausalPort):
        def factor(self, event: dict[str, Any]) -> float:
            return 2.0

        def explain(self, event: dict[str, Any]) -> str:
            return "高风险传导"

        def counterfactual(
            self,
            event: dict[str, Any],
            intervention: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return {}

    _insert_pending_event(initialized_db, severity_level="中等")
    runner = RiskEvaluationRunner(
        config_dir=temp_config_dir,
        db_path=initialized_db,
        causal_port=HighRiskCausalAdapter(),
    )
    runner.run()

    conn = get_db_connection(initialized_db)
    row = conn.execute(
        "SELECT total_score, causal_factor FROM risk_events WHERE event_id = ?",
        ("e1",),
    ).fetchone()
    conn.close()

    assert row is not None
    # 2.0 的因果因子应使总分翻倍
    assert row["causal_factor"] == 2.0
    assert row["total_score"] == 60 * 95 * 1.0 * 1.0 * 1.0 * 1.0 * 2.0


def test_run_generates_risk_reasoning_for_high_risk_events(
    initialized_db: str, temp_config_dir: str
) -> None:
    """S/M 级事件应触发 LLM 风险推理并写入 hazard_desc。"""
    _insert_pending_event(
        initialized_db,
        event_id="e-high",
        severity_level="灾难性",
        country="高风险国",
        product_category="儿童相关产品",
    )

    runner = RiskEvaluationRunner(
        config_dir=temp_config_dir,
        db_path=initialized_db,
        llm_service=LLMService(port=FixedLLMPort("高危险事件建议加强海关检验")),
    )
    runner.run()

    conn = get_db_connection(initialized_db)
    row = conn.execute(
        "SELECT rs_level, hazard_desc FROM risk_events WHERE event_id = ?",
        ("e-high",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["rs_level"] in {"S", "M"}
    assert "高危险事件建议加强海关检验" in row["hazard_desc"]


def test_evaluate_event_compat_signature(
    initialized_db: str, temp_config_dir: str
) -> None:
    """evaluate_event(event, conn) 兼容旧 RiskModel 签名。"""
    runner = RiskEvaluationRunner(config_dir=temp_config_dir, db_path=initialized_db)
    event = {
        "event_id": "e-compat",
        "severity_level": "中等",
        "country": "德国",
        "product_category": "普通机电",
        "hazard_type": "电气危险",
        "source_id": "test_api",
    }
    conn = get_db_connection(initialized_db)
    result = runner.evaluate_event(event, conn)
    conn.close()

    assert result["ss_score"] == 60
    assert result["rs_level"] in {"A", "L", "M", "S"}
    assert result["total_score"] > 0
