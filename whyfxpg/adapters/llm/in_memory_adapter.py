"""
In-memory LLM adapter for tests and offline mode.

Never performs network I/O. Returns pre-configured stub responses or a
safe default. Callers can inspect ``last_prompt`` to assert on the exact
prompt that was sent.
"""

from typing import Any

from ...ports.llm_port import LLMPort


class InMemoryLLMAdapter(LLMPort):
    """Fake LLM port that matches prompts against configured stubs."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default_response: str = "",
    ):
        """
        Args:
            responses: Mapping from prompt substring to response text.
                       The first matching key wins.
            default_response: Text returned when no stub matches.
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.last_prompt: str | None = None

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        prompt = self._extract_prompt(messages)
        self.last_prompt = prompt

        for needle, response in self.responses.items():
            if needle in prompt:
                return response
        return self.default_response

    @staticmethod
    def _extract_prompt(messages: list[dict[str, str]]) -> str:
        for msg in messages:
            if msg.get("role") == "user":
                return msg.get("content", "")
        # fall back to concatenating all contents
        return "\n".join(m.get("content", "") for m in messages if "content" in m)

    def __repr__(self) -> str:
        return f"InMemoryLLMAdapter(stubs={list(self.responses.keys())})"
