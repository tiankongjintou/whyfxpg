"""Tests for the RuleEngine seam (T16).

Covers rule repository, SQLite compiler, Pandas/sandbox compiler, RuleEngine
service, and AlertEngine integration. All tests use local fixtures or in-memory
databases so they do not depend on the production whyfxpg.db or real configs.
"""

import json
from datetime import datetime
from typing import Any

from whyfxpg.adapters.alerts import InMemoryAlertPublisher
from whyfxpg.adapters.rules import (
    FileRuleRepositoryAdapter,
    InMemoryRuleRepositoryAdapter,
    SqliteRuleCompilerAdapter,
)
from whyfxpg.config.models import AlertRule
from whyfxpg.core.alert_engine import AlertEngine
from whyfxpg.core.db import get_db_connection
from whyfxpg.core.rule_engine import RuleEngine, RuleRegressionSuite
from whyfxpg.core.stores import AlertStore, UnitOfWork
from whyfxpg.ports.rule_compiler import RuleContext


def _rule(d: dict) -> AlertRule:
    """Helper to build an AlertRule from a dict."""
    return AlertRule.from_dict(d)


def test_compile_all_rules_from_fixture_config(temp_config_dir: str) -> None:
    """All rules from alert_rules.yaml compile into a deterministic QueryPlan."""
    compiler = SqliteRuleCompilerAdapter()
    repo = FileRuleRepositoryAdapter(temp_config_dir)
    for rule in repo.list():
        compiled = compiler.compile(rule)
        assert compiled.rule_id == rule.rule_id
        assert compiled.version_id == rule.version_id
        assert compiled.query_plan.operation
        assert compiled.query_plan.source


def test_unsupported_rule_type_returns_empty_outcome() -> None:
    """An unsupported condition type yields a graceful outcome with no matches."""
    compiler = SqliteRuleCompilerAdapter()
    rule = _rule(
        {
            "rule_id": "unknown_rule",
            "name": "Unknown",
            "condition": {"type": "totally_unknown"},
            "severity": "low",
        }
    )
    compiled = compiler.compile(rule)
    # The compiler only needs a non-None store for the value check; we can pass a
    # minimal object because the unsupported handler does not touch it.
    outcome = compiler.evaluate(compiled, RuleContext(store=object()))
    assert outcome.triggered is False
    assert outcome.matched_rows == []
    assert "未支持" in outcome.natural_language_summary


def test_sqlite_threshold_evaluation(initialized_db: str) -> None:
    """SQLite compiler evaluates a threshold rule against the real DB seam."""
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
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
            "e1", "p1", "test_api", "https://example.com/", now[:10], "title",
            "产品A", "品牌A", "M1", "1234", "普通机电", "德国",
            "MfrA", "电气危险", "电击", "严重", 95,
            "可能", 95, 1.0, 1.0, 1.0, 1.0, 9000, "S", "",
            "text", now, now, "1.0", "1.0",
            0.5, "auto",
        ),
    )
    conn.commit()
    conn.close()

    rule = _rule(
        {
            "rule_id": "test_threshold",
            "name": "严重事件",
            "condition": {"type": "threshold", "values": ["严重"]},
            "severity": "high",
        }
    )
    with UnitOfWork(initialized_db) as uow:
        store = AlertStore(uow)
        compiler = SqliteRuleCompilerAdapter()
        compiled = compiler.compile(rule)
        outcome = compiler.evaluate(compiled, RuleContext(store=store, now=datetime.now()))  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        assert outcome.triggered is True
        assert len(outcome.matched_rows) == 1
        assert outcome.matched_rows[0]["object_type"] == "event"
        assert outcome.matched_rows[0]["object_value"] == "e1"
        assert outcome.query_plan.operation == "threshold"


def test_sqlite_aggregate_evaluation(initialized_db: str) -> None:
    """SQLite compiler evaluates a count_by_dimension aggregate rule."""
    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    for i in range(2):
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
                f"agg{i}", f"p{i}", "test_api", "https://example.com/", now[:10], "title",
                "产品A", "品牌A", "M1", "1234", "普通机电", "测试国",
                "MfrA", "电气危险", "电击", "中等", 60,
                "可能", 95, 1.0, 1.0, 1.0, 1.0, 5000, "M", "",
                "text", now, now, "1.0", "1.0",
                0.5, "auto",
            ),
        )
    conn.commit()
    conn.close()

    rule = _rule(
        {
            "rule_id": "test_country_burst",
            "name": "国别聚集",
            "condition": {
                "type": "count_by_dimension",
                "dimension": "country",
                "window": "30d",
                "threshold": 2,
            },
            "severity": "medium",
        }
    )
    with UnitOfWork(initialized_db) as uow:
        store = AlertStore(uow)
        compiler = SqliteRuleCompilerAdapter()
        compiled = compiler.compile(rule)
        outcome = compiler.evaluate(compiled, RuleContext(store=store, now=datetime.now()))  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        assert outcome.triggered is True
        assert any(row["object_value"] == "测试国" for row in outcome.matched_rows)
        assert outcome.query_plan.operation == "aggregate"


def test_pandas_threshold_sandbox() -> None:
    """Pandas compiler evaluates a threshold rule against an in-memory fixture."""
    rule = _rule(
        {
            "rule_id": "test_threshold_sandbox",
            "name": "Sandbox threshold",
            "condition": {"type": "threshold", "values": ["严重"]},
            "severity": "high",
        }
    )
    fixture = [
        {"event_id": "e1", "severity_level": "严重", "title": "t1"},
        {"event_id": "e2", "severity_level": "中等", "title": "t2"},
    ]
    engine = RuleEngine()
    result = engine.sandbox(rule, fixture)
    assert result.error is None
    assert result.outcome is not None
    assert result.outcome.triggered is True
    assert len(result.outcome.matched_rows) == 1
    assert result.outcome.matched_rows[0]["object_value"] == "e1"


def test_pandas_aggregate_sandbox() -> None:
    """Pandas compiler evaluates a count_by_dimension aggregate rule in sandbox."""
    rule = _rule(
        {
            "rule_id": "test_agg_sandbox",
            "name": "Sandbox aggregate",
            "condition": {
                "type": "count_by_dimension",
                "dimension": "country",
                "window": "30d",
                "threshold": 2,
            },
            "severity": "medium",
        }
    )
    today = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    fixture = [
        {"event_id": "e1", "country": "测试国", "publish_date": today},
        {"event_id": "e2", "country": "测试国", "publish_date": today},
        {"event_id": "e3", "country": "其他国", "publish_date": today},
    ]
    engine = RuleEngine()
    result = engine.sandbox(rule, fixture)
    assert result.error is None
    assert result.outcome.triggered is True  # type: ignore[union-attr]
    values = {row["object_value"] for row in result.outcome.matched_rows}  # type: ignore[union-attr]
    assert "测试国" in values


def test_pandas_trend_sandbox(monkeypatch: Any) -> None:
    """Pandas compiler evaluates a month-over-month growth trend rule."""
    import whyfxpg.core.rule_engine as rule_engine_module

    monkeypatch.setattr(
        rule_engine_module, "time_now", lambda: datetime(2026, 7, 15)  # noqa: DTZ001 — 刻意用法(见 TD03)
    )
    rule = _rule(
        {
            "rule_id": "test_trend_sandbox",
            "name": "Sandbox trend",
            "condition": {
                "type": "month_over_month_growth",
                "dimension": "country",
                "growth_rate": 1.0,
                "min_events": 2,
            },
            "severity": "medium",
        }
    )
    # Current month is July, previous is June for the test fixture.
    fixture = [
        {"event_id": "e1", "country": "测试国", "publish_date": "2026-07-01"},
        {"event_id": "e2", "country": "测试国", "publish_date": "2026-07-02"},
        {"event_id": "e3", "country": "测试国", "publish_date": "2026-07-03"},
        {"event_id": "e4", "country": "测试国", "publish_date": "2026-06-01"},
    ]
    engine = RuleEngine()
    result = engine.sandbox(rule, fixture)
    assert result.error is None
    assert result.outcome.triggered is True  # type: ignore[union-attr]
    assert any(row["object_value"] == "测试国" for row in result.outcome.matched_rows)  # type: ignore[union-attr]


def test_rule_engine_explain() -> None:
    """RuleEngine can explain an outcome in natural language."""
    rule = _rule(
        {
            "rule_id": "test_explain",
            "name": "Explainable",
            "condition": {"type": "threshold", "values": ["严重"]},
        }
    )
    fixture = [{"event_id": "e1", "severity_level": "严重", "title": "t1"}]
    engine = RuleEngine()
    result = engine.sandbox(rule, fixture)
    explanation = engine.explain(result.outcome)  # type: ignore[arg-type]
    assert "命中" in explanation
    assert result.outcome.rule_id in explanation  # type: ignore[union-attr]


def test_in_memory_rule_repository() -> None:
    """In-memory repository supports full CRUD."""
    repo = InMemoryRuleRepositoryAdapter()
    rule = _rule(
        {
            "rule_id": "r1",
            "name": "R1",
            "condition": {"type": "threshold", "values": ["严重"]},
        }
    )
    repo.save(rule)
    assert repo.load("r1").name == "R1"
    assert len(repo.list()) == 1
    repo.delete("r1")
    assert repo.list() == []


def test_file_rule_repository_persists_rules(temp_config_dir: str) -> None:
    """File-based repository can save and reload a rule to YAML."""
    repo = FileRuleRepositoryAdapter(temp_config_dir)
    rule = _rule(
        {
            "rule_id": "new_rule",
            "name": "新增规则",
            "condition": {"type": "threshold", "values": ["灾难性"]},
            "severity": "high",
        }
    )
    repo.save(rule)
    reloaded = repo.load("new_rule")
    assert reloaded.name == "新增规则"
    assert reloaded.severity == "high"
    repo.delete("new_rule")
    assert "new_rule" not in [r.rule_id for r in repo.list()]


def test_alert_engine_uses_rule_engine(initialized_db: str) -> None:
    """AlertEngine can be wired with an explicit RuleEngine and in-memory repository."""
    rule = _rule(
        {
            "rule_id": "explicit_threshold",
            "name": "Explicit",
            "condition": {"type": "threshold", "values": ["严重"]},
            "severity": "high",
        }
    )
    publisher = InMemoryAlertPublisher()
    repo = InMemoryRuleRepositoryAdapter([rule])
    engine = AlertEngine(
        db_path=initialized_db,
        publisher_factory=lambda store: publisher,
        rule_repository=repo,
    )

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
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
            "e_explicit", "p_explicit", "test_api", "https://example.com/", now[:10], "title",
            "产品A", "品牌A", "M1", "1234", "普通机电", "德国",
            "MfrA", "电气危险", "电击", "严重", 95,
            "可能", 95, 1.0, 1.0, 1.0, 1.0, 9000, "S", "",
            "text", now, now, "1.0", "1.0",
            0.5, "auto",
        ),
    )
    conn.commit()
    conn.close()

    result = engine.run()
    assert result["status"] == "success"
    assert result["records_created"] == 1
    assert publisher.records[0]["rule_id"] == "explicit_threshold"


def test_alert_engine_includes_explanation_in_alert(initialized_db: str) -> None:
    """Alert records can carry an explanation JSON produced by the rule engine."""
    rule = _rule(
        {
            "rule_id": "explained_rule",
            "name": "Explained",
            "condition": {"type": "threshold", "values": ["严重"]},
            "severity": "high",
        }
    )

    class PublishingRuleEngine(RuleEngine):
        """RuleEngine that attaches the outcome explanation to each alert."""

        def evaluate(self, compiled, context=None):
            outcome = super().evaluate(compiled, context)
            for row in outcome.matched_rows:
                row["explanation_json"] = json.dumps(
                    {
                        "rule_id": outcome.rule_id,
                        "matched_count": len(outcome.matched_rows),
                        "summary": outcome.natural_language_summary,
                    },
                    ensure_ascii=False,
                )
            return outcome

    publisher = InMemoryAlertPublisher()
    repo = InMemoryRuleRepositoryAdapter([rule])
    engine = AlertEngine(
        db_path=initialized_db,
        publisher_factory=lambda store: publisher,
        rule_repository=repo,
        rule_engine=PublishingRuleEngine(compiler=SqliteRuleCompilerAdapter()),
    )

    conn = get_db_connection(initialized_db)
    cursor = conn.cursor()
    now = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
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
            "e_exp", "p_exp", "test_api", "https://example.com/", now[:10], "title",
            "产品A", "品牌A", "M1", "1234", "普通机电", "德国",
            "MfrA", "电气危险", "电击", "严重", 95,
            "可能", 95, 1.0, 1.0, 1.0, 1.0, 9000, "S", "",
            "text", now, now, "1.0", "1.0",
            0.5, "auto",
        ),
    )
    conn.commit()
    conn.close()

    engine.run()
    assert publisher.records[0].get("explanation_json") is not None


def test_pandas_risk_level_change_sandbox() -> None:
    """Pandas compiler evaluates a risk_level_change rule on a summary fixture."""
    rule = _rule(
        {
            "rule_id": "test_risk_level_change",
            "name": "Risk level change",
            "condition": {"type": "risk_level_change", "to": ["M", "S"], "window": "30d"},
            "severity": "high",
        }
    )
    today = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    fixture = [
        {
            "product_id": "p1",
            "latest_rs_level": "S",
            "latest_total_score": 9000,
            "updated_at": today,
        },
        {
            "product_id": "p2",
            "latest_rs_level": "L",
            "latest_total_score": 1000,
            "updated_at": today,
        },
    ]
    engine = RuleEngine()
    result = engine.sandbox(rule, fixture)
    assert result.error is None
    assert result.outcome.triggered is True  # type: ignore[union-attr]
    assert len(result.outcome.matched_rows) == 1  # type: ignore[union-attr]
    assert result.outcome.matched_rows[0]["object_value"] == "p1"  # type: ignore[union-attr]


def test_pandas_novel_pattern_sandbox() -> None:
    """Pandas compiler evaluates a novel_pattern rule on a fixture."""
    rule = _rule(
        {
            "rule_id": "test_novel_pattern",
            "name": "Novel pattern",
            "condition": {
                "type": "novel_pattern",
                "dimension": "hazard_type",
                "group_by": "product_category",
                "lookback": "365d",
            },
            "severity": "low",
        }
    )
    today = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
    fixture = [
        {"event_id": "e1", "product_category": "普通机电", "hazard_type": "电气危险", "publish_date": today},
        {"event_id": "e2", "product_category": "普通机电", "hazard_type": "电气危险", "publish_date": today},
        {"event_id": "e3", "product_category": "普通机电", "hazard_type": "机械危险", "publish_date": today},
    ]
    engine = RuleEngine()
    result = engine.sandbox(rule, fixture)
    assert result.error is None
    assert result.outcome.triggered is True  # type: ignore[union-attr]
    # Two distinct (category, hazard_type) combinations appear.
    assert len(result.outcome.matched_rows) == 2  # type: ignore[union-attr]


def test_rule_regression_suite_diffs_outcomes() -> None:
    """RuleRegressionSuite detects when rule outcomes change against a fixture."""
    rule = _rule(
        {
            "rule_id": "test_reg",
            "name": "Regression",
            "condition": {"type": "threshold", "values": ["严重"]},
        }
    )
    fixture = [
        {"event_id": "e1", "severity_level": "严重", "title": "t1"},
    ]
    suite = RuleRegressionSuite()
    report = suite.run([rule], fixture, baseline={"test_reg": {"triggered": False, "matched_count": 0}})
    assert report["total"] == 1
    assert report["changed"] == 1
    assert report["reports"]["test_reg"]["status"] == "changed"
    assert report["reports"]["test_reg"]["current_count"] == 1

    report_unchanged = suite.run([rule], fixture, baseline={"test_reg": {"triggered": True, "matched_count": 1}})
    assert report_unchanged["changed"] == 0
    assert report_unchanged["reports"]["test_reg"]["status"] == "unchanged"
