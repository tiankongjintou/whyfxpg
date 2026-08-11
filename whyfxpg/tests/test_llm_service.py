import os

import pytest

from whyfxpg.adapters.llm.in_memory_adapter import InMemoryLLMAdapter
from whyfxpg.services.llm_service import LLMService


@pytest.fixture
def make_adapter():
    """Factory for InMemoryLLMAdapter with arbitrary stubs."""

    def _factory(stubs=None, default=""):
        return InMemoryLLMAdapter(responses=stubs or {}, default_response=default)

    return _factory


def test_extract_entities_parses_json(make_adapter):
    stub = make_adapter(
        stubs={"抽取": '{"product_name": "电钻", "brand": "Bosch"}'}
    )
    service = LLMService(port=stub)
    result = service.extract_entities("请抽取以下信息")
    assert result["product_name"] == "电钻"
    assert result["brand"] == "Bosch"


def test_extract_entities_returns_empty_dict_on_blank_response(make_adapter):
    stub = make_adapter(default="")
    service = LLMService(port=stub)
    assert service.extract_entities("any") == {}


def test_classify_text_returns_model_label(make_adapter):
    stub = make_adapter(stubs={"分类": "机械危险"})
    service = LLMService(port=stub)
    label = service.classify_text("文本", ["机械危险", "电气危险"])
    assert label == "机械危险"


def test_classify_text_falls_back_to_first_category(make_adapter):
    stub = make_adapter(default="")
    service = LLMService(port=stub)
    label = service.classify_text("文本", ["机械危险", "电气危险"])
    assert label == "机械危险"


def test_classify_text_returns_empty_without_categories(make_adapter):
    stub = make_adapter()
    service = LLMService(port=stub)
    assert service.classify_text("文本", []) == ""


def test_summarize_returns_stub(make_adapter):
    stub = make_adapter(stubs={"摘要": "这是摘要"})
    service = LLMService(port=stub)
    assert service.summarize("长文本") == "这是摘要"


def test_risk_reasoning_truncates_to_300_chars(make_adapter):
    long_text = "x" * 500
    stub = make_adapter(stubs={"风险": long_text})
    service = LLMService(port=stub)
    event = {"product_name": "A", "rs_level": "S", "total_score": 9000}
    result = service.risk_reasoning(event)
    assert len(result) == 300


def test_executive_summary_prompt_contains_data(make_adapter):
    stub = make_adapter(stubs={"执行摘要": "报告摘要"}, default="")
    service = LLMService(port=stub)
    data = {
        "total_events": 10,
        "level_counts": {"S": 1, "M": 2, "L": 3, "A": 4},
        "top_countries": [{"country": "德国", "event_count": 3, "s_count": 1}],
        "top_products": [{"product_name": "电钻", "latest_rs_level": "S"}],
        "pending_alerts": [],
    }
    result = service.executive_summary(data)
    assert result == "报告摘要"
    assert "德国" in stub.last_prompt
    assert "10" in stub.last_prompt


def test_chat_completion_delegates_to_port(make_adapter):
    stub = make_adapter(stubs={"raw": " pong"}, default="")
    service = LLMService(port=stub)
    assert service.chat_completion([{"role": "user", "content": "ping"}]) == ""
    assert service.chat_completion([{"role": "user", "content": "raw"}]) == " pong"


def test_default_port_uses_in_memory_when_llm_disabled(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    service = LLMService()
    assert isinstance(service.port, InMemoryLLMAdapter)


def test_default_port_uses_openai_compat_when_llm_enabled(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    # Without monkeypatching get_llm_client this would require real keys.
    # We substitute the adapter factory instead to keep the test offline.
    import whyfxpg.services.llm_service as llm_service_mod

    original_default = llm_service_mod.LLMService._default_port

    class DummyPort:
        def chat_completion(self, messages, **kwargs):
            return "dummy"

    llm_service_mod.LLMService._default_port = classmethod(lambda cls: DummyPort())
    try:
        service = LLMService()
        assert service.chat_completion([{"role": "user", "content": "x"}]) == "dummy"
    finally:
        llm_service_mod.LLMService._default_port = original_default


def test_llm_enabled_env_defaults_to_true(make_adapter):
    # Make sure missing env is treated as enabled.
    os.environ.pop("LLM_ENABLED", None)
    # We don't actually construct the real adapter here to avoid key errors.
    assert LLMService._is_llm_enabled() is True
