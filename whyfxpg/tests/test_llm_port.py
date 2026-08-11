from typing import Any

import pytest

from whyfxpg.adapters.llm.in_memory_adapter import InMemoryLLMAdapter
from whyfxpg.adapters.llm.openai_compat_adapter import OpenAICompatAdapter
from whyfxpg.ports.llm_port import LLMPort


class _MockResponse:
    def __init__(self, data: dict[str, Any], status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakePost:
    def __init__(self, response_data: dict[str, Any], status_code: int = 200):
        self.calls: list[dict[str, Any]] = []
        self.response = _MockResponse(response_data, status_code)

    def __call__(self, url: str, **kwargs: Any) -> _MockResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def test_llm_port_is_abstract():
    with pytest.raises(TypeError):
        LLMPort()


def test_in_memory_adapter_returns_matching_stub():
    adapter = InMemoryLLMAdapter(
        responses={"风险": "高风险", "一般": "一般"}, default_response="默认"
    )
    assert adapter.chat_completion([{"role": "user", "content": "存在风险情况"}]) == "高风险"


def test_in_memory_adapter_returns_default_when_no_match():
    adapter = InMemoryLLMAdapter(
        responses={"未命中": "不会返回"}, default_response="兜底"
    )
    assert adapter.chat_completion([{"role": "user", "content": "完全不相关"}]) == "兜底"


def test_in_memory_adapter_records_last_prompt():
    adapter = InMemoryLLMAdapter()
    adapter.chat_completion([{"role": "user", "content": "hello"}])
    assert adapter.last_prompt == "hello"


def test_openai_compat_adapter_posts_and_extracts_content(monkeypatch):
    env = {
        "DEFAULT_LLM_PROVIDER": "kimi",
        "KIMI_API_KEY": "kimi-test-key",
        "KIMI_BASE_URL": "https://api.moonshot.cn/v1",
        "KIMI_MODEL": "kimi-for-coding",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    fake_post = _FakePost({"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr("httpx.Client.post", fake_post)

    adapter = OpenAICompatAdapter()
    result = adapter.chat_completion([{"role": "user", "content": "hi"}])
    assert result == "ok"
    assert len(fake_post.calls) == 1
    payload = fake_post.calls[0]["json"]
    assert payload["model"] == "kimi-for-coding"
    assert "temperature" not in payload
    assert payload["messages"][0]["content"] == "hi"


def test_openai_compat_adapter_omits_temperature_for_kimi_only(monkeypatch):
    env = {
        "DEFAULT_LLM_PROVIDER": "minimax",
        "MINIMAX_API_KEY": "mm-test-key",
        "MINIMAX_BASE_URL": "https://api.minimax.chat/v1",
        "MINIMAX_MODEL": "MiniMax-Text-01",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    fake_post = _FakePost({"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr("httpx.Client.post", fake_post)

    adapter = OpenAICompatAdapter(provider="minimax")
    adapter.chat_completion([{"role": "user", "content": "hi"}], temperature=0.1)
    payload = fake_post.calls[0]["json"]
    assert payload["temperature"] == 0.1


def test_openai_compat_adapter_raises_on_http_error(monkeypatch):
    env = {
        "DEFAULT_LLM_PROVIDER": "kimi",
        "KIMI_API_KEY": "k",
        "KIMI_BASE_URL": "https://api.moonshot.cn/v1",
        "KIMI_MODEL": "kimi-for-coding",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    fake_post = _FakePost({}, status_code=401)
    monkeypatch.setattr("httpx.Client.post", fake_post)

    adapter = OpenAICompatAdapter()
    with pytest.raises(RuntimeError):
        adapter.chat_completion([{"role": "user", "content": "x"}])


def test_openai_compat_adapter_repr_contains_provider(monkeypatch):
    env = {
        "DEFAULT_LLM_PROVIDER": "volcano",
        "VOLCANO_API_KEY": "v",
        "VOLCANO_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        "VOLCANO_MODEL": "doubao-pro",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    adapter = OpenAICompatAdapter()
    assert "volcano" in repr(adapter).lower()
