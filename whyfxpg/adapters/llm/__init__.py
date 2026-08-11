"""
LLM adapter package.
"""
from .in_memory_adapter import InMemoryLLMAdapter
from .openai_compat_adapter import OpenAICompatAdapter

__all__ = ["InMemoryLLMAdapter", "OpenAICompatAdapter"]
