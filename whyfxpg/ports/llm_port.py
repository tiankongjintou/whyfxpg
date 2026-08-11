"""
LLM Port: abstract boundary for all LLM calls.

Domain code (ExtractEngine, RiskModel, ReportGenerator, etc.)
should depend only on this abstraction, never on a concrete
provider implementation.
"""

from abc import ABC, abstractmethod
from typing import Any


class LLMPort(ABC):
    """Abstract LLM port.

    Implementations must expose a single low-level
    ``chat_completion`` method that accepts an OpenAI-compatible
    message list and returns the raw text content.

    Provider-specific quirks (model aliases, temperature handling,
    retry/backoff) are encapsulated inside the adapter.
    """

    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = 0.3,
        max_tokens: int | None = 1000,
        **kwargs: Any,
    ) -> str:
        """Execute a chat completion and return the generated text."""
        raise NotImplementedError
