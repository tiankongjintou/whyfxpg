"""OpenAI-compatible LLM adapter.

Directly calls the provider's OpenAI-compatible chat completion endpoint using
``httpx``. This completes the LLMPort seam and removes the dependency on the
legacy ``core.llm_client`` singleton.
"""

from typing import Any

import httpx

from ...ports.llm_port import LLMPort
from ._provider_config import get_provider_config


class OpenAICompatAdapter(LLMPort):
    """Adapter for Kimi / MiniMax / Volcano via OpenAI-compatible HTTP APIs."""

    def __init__(self, provider: str | None = None, timeout: float = 60.0):
        """
        Args:
            provider: Provider name (kimi | minimax | volcano). If omitted,
                      ``DEFAULT_LLM_PROVIDER`` from the environment is used.
            timeout: Request timeout in seconds.
        """
        self._provider_name = provider
        self._timeout = timeout
        self._config: dict[str, Any] | None = None
        self._client: httpx.Client | None = None

    @property
    def config(self) -> dict[str, Any]:
        if self._config is None:
            self._config = get_provider_config(self._provider_name)
        return self._config

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            cfg = self.config
            self._client = httpx.Client(
                base_url=cfg["base_url"],
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        return self._client

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = 0.3,
        max_tokens: int | None = 1000,
        **kwargs: Any,
    ) -> str:
        cfg = self.config
        # kimi-for-coding only accepts temperature=1.0; treat other values as None.
        if cfg["provider"] == "kimi" and temperature != 1.0:
            temperature = None

        payload: dict[str, Any] = {
            "model": cfg["model"],
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        response = self.client.post(cfg["chat_path"], json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def __repr__(self) -> str:
        cfg = self.config
        return (
            f"OpenAICompatAdapter(provider={cfg['provider']}, model={cfg['model']}, "
            f"base_url={cfg['base_url']})"
        )
