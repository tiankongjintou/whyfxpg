"""
LLM Service: semantic operations built on the LLM port.

All domain code should consume LLM capabilities through this service.
It owns prompt templates, response parsing, and safe fallbacks.
The actual provider protocol is delegated to an ``LLMPort`` adapter.
"""

import json
import os
import re
from typing import Any

from ..adapters.llm.in_memory_adapter import InMemoryLLMAdapter
from ..adapters.llm.openai_compat_adapter import OpenAICompatAdapter
from ..ports.llm_port import LLMPort


class LLMService:
    """High-level LLM service with provider-agnostic semantic methods."""

    _ENTITY_PROMPT = (
        "你是一个专业的进口机电产品风险信息抽取助手。请从以下文本中抽取关键信息，"
        "以严格的JSON格式返回，只输出JSON，不要任何其他文字。\n\n"
        "文本：\n{text}\n\n"
        "需要抽取的字段（如果无法确定，填写\"unknown\"）：\n"
        "product_name（产品名称）, brand（品牌）, model（型号）, "
        "hs_code（海关编码）, country（原产国）, manufacturer（制造商）, "
        "hazard_type（危害类型）, severity_level（严重程度：高/中/低）, "
        "publish_date（发布日期，格式YYYY-MM-DD）, standards（适用标准）\n\n"
        "JSON格式："
    )

    _CLASSIFY_PROMPT = (
        "请将以下文本分类到给定类别之一：{categories}。"
        "只返回类别名称，不解释。\n\n文本：\n{text}"
    )

    _SUMMARIZE_PROMPT = (
        "请为以下文本生成不超过{max_words}字的中文摘要，"
        "只输出摘要，不解释。\n\n文本：\n{text}"
    )

    _RISK_REASONING_PROMPT = (
        "给定以下进口机电产品风险事件，请生成50字的风险解释和海关检验建议：\n"
        "- 产品：{product_name}\n"
        "- 品牌：{brand}\n"
        "- 原产国：{country}\n"
        "- 制造商：{manufacturer}\n"
        "- 危害类型：{hazard_type}\n"
        "- 严重程度：{severity_level}\n"
        "- 风险等级：{rs_level}（总分：{total_score}）\n\n"
        "请直接输出风险解释和建议。"
    )

    _EXECUTIVE_SUMMARY_PROMPT = (
        "你是一个海关进口机电产品风险评估报告的摘要撰写助手。"
        "根据以下数据，生成一段不超过200字的中文执行摘要：\n"
        "- 本期共纳入风险事件 {total_events} 条\n"
        "- 风险等级分布：S级{s_count}条，M级{m_count}条，L级{l_count}条，A级{a_count}条\n"
        "- 风险最高的国家：{top_country}（{top_country_count}起，S级{top_country_s_count}条）\n"
        "- 风险最高的产品：{top_product}（风险等级{top_product_level}）\n"
        "- 当前待处理预警 {pending_alerts} 条\n\n"
        "摘要应包含：1）总体风险评估，2）主要风险来源，3）行动建议。"
    )

    def __init__(self, port: LLMPort | None = None):
        """
        Args:
            port: Explicit LLM port adapter. When None, the service creates one
                  from environment: ``OpenAICompatAdapter`` if ``LLM_ENABLED`` is
                  true, otherwise an ``InMemoryLLMAdapter`` returning safe defaults.
        """
        self._port = port or self._default_port()

    @property
    def port(self) -> LLMPort:
        return self._port

    @staticmethod
    def _is_llm_enabled() -> bool:
        value = os.getenv("LLM_ENABLED", "true").lower().strip()
        return value in ("true", "1", "yes", "on")

    @classmethod
    def _default_port(cls) -> LLMPort:
        if cls._is_llm_enabled():
            return OpenAICompatAdapter()
        return InMemoryLLMAdapter()

    def chat_completion(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Raw completion access. Prefer semantic methods."""
        return self._port.chat_completion(messages, **kwargs)

    def extract_entities(
        self,
        text: str,
        prompt_template: str | None = None,
    ) -> dict[str, Any]:
        """Extract structured entities from free text."""
        prompt = (prompt_template or self._ENTITY_PROMPT).format(text=text[:8000])
        try:
            response = self._port.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=800,
            )
            if not response or not response.strip():
                return {}
            return self._parse_json(response)
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return {"error": str(e), "raw": ""}

    def classify_text(
        self,
        text: str,
        categories: list[str],
        prompt_template: str | None = None,
    ) -> str:
        """Classify text into one of the given categories."""
        if not categories:
            return ""
        prompt = (prompt_template or self._CLASSIFY_PROMPT).format(
            categories=", ".join(categories),
            text=text[:4000],
        )
        try:
            response = self._port.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50,
            )
            label = response.strip()
            return label if label else categories[0]
        except Exception:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return categories[0]

    def summarize(self, text: str, max_words: int = 200) -> str:
        """Generate a concise Chinese summary."""
        prompt = self._SUMMARIZE_PROMPT.format(
            max_words=max_words,
            text=text[:6000],
        )
        try:
            response = self._port.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=max_words * 2,
            )
            return response.strip()
        except Exception:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return ""

    def risk_reasoning(
        self,
        event: dict[str, Any],
        prompt_template: str | None = None,
    ) -> str:
        """Generate a short risk explanation for a scored event."""
        prompt = (prompt_template or self._RISK_REASONING_PROMPT).format(
            product_name=event.get("product_name", "unknown"),
            brand=event.get("brand", "unknown"),
            country=event.get("country", "unknown"),
            manufacturer=event.get("manufacturer", "unknown"),
            hazard_type=event.get("hazard_type", "unknown"),
            severity_level=event.get("severity_level", "unknown"),
            rs_level=event.get("rs_level", "unknown"),
            total_score=event.get("total_score", "unknown"),
        )
        try:
            response = self._port.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            return response.strip()[:300]
        except Exception:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return ""

    def executive_summary(self, data: dict[str, Any]) -> str:
        """Generate an executive summary for the report."""
        top_country = data.get("top_countries", [{}])[0] if data.get("top_countries") else {}
        top_product = data.get("top_products", [{}])[0] if data.get("top_products") else {}
        level_counts = data.get("level_counts", {})
        prompt = self._EXECUTIVE_SUMMARY_PROMPT.format(
            total_events=data.get("total_events", 0),
            s_count=level_counts.get("S", 0),
            m_count=level_counts.get("M", 0),
            l_count=level_counts.get("L", 0),
            a_count=level_counts.get("A", 0),
            top_country=top_country.get("country", "未知"),
            top_country_count=top_country.get("event_count", 0),
            top_country_s_count=top_country.get("s_count", 0),
            top_product=top_product.get("product_name", "未知"),
            top_product_level=top_product.get("latest_rs_level", "?"),
            pending_alerts=len(data.get("pending_alerts", [])),
        )
        try:
            return self._port.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400,
            ).strip()
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return f"（执行摘要生成失败：{e}）"

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Parse JSON from an LLM response, tolerating markdown wrappers."""
        text = text.strip()

        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        code_block_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            text,
            re.DOTALL,
        )
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass

        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {"raw": text, "parse_error": "无法解析为JSON"}
