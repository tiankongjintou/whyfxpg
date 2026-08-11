"""Shared LLM provider configuration.

Kept in a separate module so the OpenAI-compatible adapter (and any future
adapters) can read provider endpoints without depending on the legacy
``core.llm_client`` singleton.
"""

import os
from typing import Any


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


_PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "kimi": {
        "api_key_env": "KIMI_API_KEY",
        "base_url_env": "KIMI_BASE_URL",
        "model_env": "KIMI_MODEL",
        "default_base_url": "https://api.kimi.com/coding/v1",
        "default_model": "kimi-for-coding",
        "chat_path": "/chat/completions",
    },
    "minimax": {
        "api_key_env": "MINIMAX_API_KEY",
        "base_url_env": "MINIMAX_BASE_URL",
        "model_env": "MINIMAX_MODEL",
        "default_base_url": "https://api.minimaxi.com/v1",
        "default_model": "MiniMax-M2.7-highspeed",
        "chat_path": "/chat/completions",
    },
    "volcano": {
        "api_key_env": "VOLCANO_API_KEY",
        "base_url_env": "VOLCANO_BASE_URL",
        "model_env": "VOLCANO_MODEL",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "default_model": "deepseek-v4-flash-260425",
        "chat_path": "/chat/completions",
    },
}


def get_provider_config(provider: str | None = None) -> dict[str, Any]:
    """Return resolved configuration for the requested provider.

    Falls back to ``DEFAULT_LLM_PROVIDER`` and then ``minimax``.
    """
    name = provider or _env("DEFAULT_LLM_PROVIDER", "minimax")
    cfg = _PROVIDER_CONFIG.get(name)
    if cfg is None:
        raise ValueError(f"Unsupported LLM provider: {name}")

    api_key = _env(cfg["api_key_env"])
    base_url = _env(cfg["base_url_env"], cfg["default_base_url"])
    model = _env(cfg["model_env"], cfg["default_model"])

    if not api_key:
        raise ValueError(
            f"Missing API key for provider '{name}'. Set {cfg['api_key_env']} in the environment."
        )

    return {
        "provider": name,
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "chat_path": cfg.get("chat_path", "/chat/completions"),
    }
