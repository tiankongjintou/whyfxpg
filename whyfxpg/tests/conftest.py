from pathlib import Path
from typing import Any

import pytest
import yaml

from whyfxpg.core.db import get_db_connection
from whyfxpg.migrations import MigrationRunner


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """返回一个临时 SQLite 数据库路径，测试不污染生产 whyfxpg.db"""
    return str(tmp_path / "test.db")


@pytest.fixture
def initialized_db(tmp_db_path: str) -> str:
    """初始化临时数据库，包含完整表结构（含因果图谱表）"""
    conn = get_db_connection(tmp_db_path)
    try:
        MigrationRunner(conn).run()
        conn.commit()
    finally:
        conn.close()
    return tmp_db_path


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> str:
    """创建最小可运行配置目录，避免测试依赖外部网络或真实配置版本"""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()

    sources = {
        "sources": {
            "test_api": {
                "name": "测试 API",
                "url": "https://example.com/recalls",
                "source_type": "web",
                "enabled": True,
                "check_interval": "1h",
                "delay": 0,
            }
        }
    }

    risk_model = {
        "version": "1.0",
        "severity_levels": {
            "灾难性": {"score": 100},
            "严重": {"default": 95},
            "中等": {"default": 60},
            "轻微": {"default": 15},
        },
        "probability_levels": {
            "非常可能": {"score": 100},
            "可能": {"default": 95},
            "不太可能": {"default": 60},
            "几乎不可能": {"default": 15},
        },
        "country_factors": {"unknown": 1.0, "测试国": 1.0},
        "product_factors": {"unknown": 1.0, "普通机电": 1.0},
        "history_factor": {"formula": "1 + 0.1 * min(event_count_12m, 5)", "max": 1.5, "min": 1.0},
        "evidence_factors": {"test_api": 1.0, "unknown": 0.9},
        "risk_level_thresholds": {"S": 8000, "M": 3000, "L": 1000, "A": 0},
    }

    extract_rules = {
        "rules": [
            {
                "rule_id": "extract_publish_date",
                "field": "publish_date",
                "method": "regex",
                "patterns": [r"(\d{4})-(\d{2})-(\d{2})"],
            },
            {
                "rule_id": "extract_hazard_type",
                "field": "hazard_type",
                "method": "keyword_map",
                "map": {"电气危险": ["电击"], "机械危险": ["夹伤"]},
                "default": "组合危险",
            },
            {
                "rule_id": "extract_severity_level",
                "field": "severity_level",
                "method": "keyword_map",
                "map": {"严重": ["住院"], "中等": ["轻伤"]},
                "default": "中等",
            },
            {
                "rule_id": "extract_country",
                "field": "country",
                "method": "regex",
                "patterns": [r"原产国[:：]\s*([^，。；\s]+)"],
                "applies_to": ["test_api"],
            },
        ]
    }

    alert_rules = {
        "rules": [
            {
                "rule_id": "high_severity_event",
                "name": "高严重度事件预警",
                "enabled": True,
                "condition": {"type": "threshold", "dimension": "severity_level", "values": ["灾难性", "严重"]},
                "severity": "high",
            },
            {
                "rule_id": "country_burst",
                "name": "国别事件聚集预警",
                "enabled": True,
                "condition": {"type": "count_by_dimension", "dimension": "country", "window": "30d", "threshold": 2},
                "severity": "medium",
            },
            {
                "rule_id": "new_hazard_type",
                "name": "新危害类型出现预警",
                "enabled": False,
                "condition": {"type": "novel_pattern", "dimension": "hazard_type", "group_by": "product_category", "lookback": "365d"},
                "severity": "low",
            },
        ]
    }

    keywords = {"product_category_keywords": {"普通机电": ["普通机电"]}}

    version_history = {"history": [{"version": "1.0", "date": "2026-01-01", "description": "init"}]}

    for name, data in [
        ("sources.yaml", sources),
        ("risk_model.yaml", risk_model),
        ("extract_rules.yaml", extract_rules),
        ("alert_rules.yaml", alert_rules),
        ("keywords.yaml", keywords),
        ("version_history.yaml", version_history),
    ]:
        (cfg_dir / name).write_text(yaml.safe_dump(data), encoding="utf-8")

    return str(cfg_dir)


class DummyLLMClient:
    """用于测试的 LLM 客户端占位，避免真实 API 调用"""

    def chat_completion(
        self,
        messages: list,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """兼容 LLMPort 的原始 completion 接口。"""
        return ""

    def extract_entities(self, text: str) -> dict[str, Any]:
        return {}

    def risk_reasoning(self, event: dict[str, Any]) -> str:
        return ""

    def report_summary(self, events: list) -> str:
        return ""


@pytest.fixture(autouse=True)
def disable_llm_calls(request: Any, monkeypatch: Any) -> None:
    """自动对所有测试禁用真实 LLM 调用（LLM adapter 自身的测试除外）。"""
    if "test_llm_port" in request.node.nodeid:
        return

    from whyfxpg.adapters.llm.openai_compat_adapter import OpenAICompatAdapter

    def _dummy_init(self, provider: Any = None, timeout: float = 60.0) -> None:
        self._provider_name = provider
        self._timeout = timeout
        self._config = None
        self._client = None

    monkeypatch.setattr(OpenAICompatAdapter, "__init__", _dummy_init)
    monkeypatch.setattr(
        OpenAICompatAdapter,
        "chat_completion",
        lambda self, messages, temperature=None, max_tokens=None, **kwargs: "",
    )
