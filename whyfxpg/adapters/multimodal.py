"""多模态处理模块

功能：
- 产品缺陷图片理解：使用视觉模型，从产品照片中识别缺陷类型和风险标签
- PDF 标准文件解析：提取关键安全条款和版本变化
- 为 extract_engine 提供多模态实体补充（图片→产品类型/缺陷）
"""

import base64
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from whyfxpg.adapters.llm.openai_compat_adapter import OpenAICompatAdapter

# ─────────────────────────────────────────────────────────────
# 产品缺陷图片理解
# ─────────────────────────────────────────────────────────────

class ImageUnderstanding:
    """
    使用视觉模型理解产品缺陷图片。
    返回：缺陷类型、风险等级建议、关键观察描述。
    """

    def __init__(self, llm_provider: str = "minimax"):
        self.llm_provider = llm_provider
        self._client: OpenAICompatAdapter | None = None

    @property
    def client(self) -> OpenAICompatAdapter:
        if self._client is None:
            self._client = OpenAICompatAdapter(provider=self.llm_provider)
        return self._client

    def understand_from_url(self, image_url: str, context: str = "") -> dict[str, Any]:
        """从图片 URL 理解产品缺陷。"""
        prompt = (
            "你是一个专业的产品安全检测专家。请分析以下产品图片，"
            "识别可能存在的缺陷或安全隐患，并返回结构化信息。\n\n"
            f"产品背景信息：{context[:500] if context else '无'}\n\n"
            "请返回以下格式的 JSON（只返回 JSON，不要其他文字）：\n"
            "{\n"
            '  "defect_type": "缺陷类型，如：绝缘层破损/电池膨胀/结构裂纹/标签缺失 等",\n'
            '  "risk_level": "高/中/低，表示该缺陷的潜在危害严重程度",\n'
            '  "description": "50字以内的图片观察描述",\n'
            '  "hazard_signals": ["关键危险信号1", "关键危险信号2"],\n'
            '  "confidence": 0.0-1.0，表示你对该判断的置信度\n'
            "}"
        )

        try:
            response = self.client.chat_completion(
                [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]}],
                temperature=0.1,
                max_tokens=600,
            )
            return self._parse_response(response)
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return {
                "defect_type": "unknown",
                "risk_level": "unknown",
                "description": f"图片理解失败：{e}",
                "hazard_signals": [],
                "confidence": 0.0,
                "error": str(e),
            }

    def understand_from_bytes(
        self,
        image_bytes: bytes,
        context: str = "",
        filename: str = "image.jpg",
    ) -> dict[str, Any]:
        """从图片字节数据理解产品缺陷（base64 编码）。"""
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        if filename.lower().endswith(".png"):
            mime = "image/png"
        elif filename.lower().endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        else:
            mime = "image/jpeg"
        data_uri = f"data:{mime};base64,{b64}"

        prompt = (
            "你是一个专业的产品安全检测专家。请分析产品图片，"
            "识别缺陷和安全隐患，返回结构化 JSON：\n"
            "{\n"
            '  "defect_type": "缺陷类型",\n'
            '  "risk_level": "高/中/低",\n'
            '  "description": "50字以内描述",\n'
            '  "hazard_signals": ["信号1", "信号2"],\n'
            '  "confidence": 0.0-1.0\n'
            "}"
        )

        try:
            response = self.client.chat_completion(
                [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]}],
                temperature=0.1,
                max_tokens=600,
            )
            return self._parse_response(response)
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return {
                "defect_type": "unknown",
                "risk_level": "unknown",
                "description": f"图片理解失败：{e}",
                "hazard_signals": [],
                "confidence": 0.0,
                "error": str(e),
            }

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any]:
        """解析 LLM 返回的 JSON"""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return {
            "defect_type": "unknown",
            "risk_level": "unknown",
            "description": text[:200],
            "hazard_signals": [],
            "confidence": 0.0,
            "parse_error": "无法解析为 JSON",
        }


# ─────────────────────────────────────────────────────────────
# PDF 标准文件解析
# ─────────────────────────────────────────────────────────────

class StandardParser:
    """
    解析 PDF 标准文件，提取关键安全条款和版本变化。
    支持：IEC/GB/EN/UL 等标准文档。
    """

    def __init__(self, llm_provider: str = "volcano"):
        self.llm_provider = llm_provider
        self._client: OpenAICompatAdapter | None = None

    @property
    def client(self) -> OpenAICompatAdapter:
        if self._client is None:
            self._client = OpenAICompatAdapter(provider=self.llm_provider)
        return self._client

    def extract_from_pdf(self, pdf_path: str) -> dict[str, Any]:
        """从 PDF 文件中提取关键标准条款。"""
        try:
            import fitz  # type: ignore[import-untyped]  # PyMuPDF 无 stub
        except ImportError:
            return {
                "standard_number": "",
                "title": "",
                "key_clauses": [],
                "version_changes": "",
                "error": "PyMuPDF 未安装，请运行 pip install pymupdf",
                "confidence": 0.0,
            }

        try:
            doc = fitz.open(pdf_path)
            text_pages = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_pages.append(text)
            doc.close()

            full_text = "\n".join(text_pages)

            std_match = re.search(
                r"(?:GB|IEC|EN|UL|ISO)[\s/-]?\d+(?:[-:]\d+)*",
                full_text,
                re.IGNORECASE,
            )
            standard_number = std_match.group() if std_match else ""

            title_match = re.search(
                r"^[A-Z][A-Z\s\-:,;]+(?:标准|Specification|Standard)",
                text_pages[0] if text_pages else "",
                re.MULTILINE,
            )
            title = title_match.group() if title_match else ""

            prompt = (
                "你是标准文件分析专家。请从以下标准文本中提取关键安全条款，"
                "并返回 JSON 格式（只返回 JSON）：\n\n"
                f"{full_text[:4000]}\n\n"
                "返回格式：\n"
                "{\n"
                '  "key_clauses": ["关键条款1", "关键条款2"],\n'
                '  "version_changes": "相比上一版本的主要变化（若无上一版本信息则写\"无法确定\"）",\n'
                '  "new_hazard_controls": ["新增的安全控制措施1", "新增的安全控制措施2"]\n'
                "}"
            )

            response = self.client.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=800,
            )

            result = self._parse_json_response(response)
            result["pdf_path"] = pdf_path
            result["pages_extracted"] = len(text_pages)
            result["standard_number"] = result.get("standard_number", standard_number)
            result["title"] = result.get("title", title)
            return result

        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return {
                "standard_number": "",
                "title": "",
                "key_clauses": [],
                "version_changes": "",
                "error": str(e),
                "confidence": 0.0,
            }

    def extract_from_bytes(self, pdf_bytes: bytes, filename: str = "standard.pdf") -> dict[str, Any]:
        """从 PDF 字节数据提取"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            return self.extract_from_pdf(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def detect_version_change(
        self,
        new_standard_text: str,
        old_standard_text: str = "",
    ) -> dict[str, Any]:
        """对比新旧版本标准，识别变化条款。"""
        prompt = (
            "你是标准差异分析专家。请对比新旧版本标准文本，"
            "识别变化条款并返回 JSON（只返回 JSON）：\n\n"
            "旧版本：\n" + (old_standard_text[:2000] or "无") + "\n\n"
            "新版本：\n" + new_standard_text[:2000] + "\n\n"
            "返回格式：\n"
            "{\n"
            '  "new_requirements": ["新增要求"],\n'
            '  "removed_requirements": ["移除的要求"],\n'
            '  "impact_assessment": "50字以内评估"\n'
            "}"
        )

        try:
            response = self.client.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=800,
            )
            return self._parse_json_response(response)
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return {
                "new_requirements": [],
                "removed_requirements": [],
                "impact_assessment": f"分析失败：{e}",
                "error": str(e),
            }

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """解析 LLM 返回的 JSON"""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return {"raw": text[:200], "parse_error": "无法解析 JSON"}


# ─────────────────────────────────────────────────────────────
# 页面图片批量抽取（辅助 extract_engine）
# ─────────────────────────────────────────────────────────────

def extract_images_from_html(html_content: str) -> list[str]:
    """从 HTML 中提取所有图片 URL。"""
    img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
    return img_pattern.findall(html_content)


def extract_main_product_image(html_content: str) -> str | None:
    """从 HTML 中选择一张最可能是产品主图的 URL。"""
    imgs = extract_images_from_html(html_content)
    if not imgs:
        return None

    for url in imgs:
        if any(x in url.lower() for x in ["avatar", "icon", "logo", "banner", "pixel", "tracking"]):
            continue
        return url

    return imgs[0] if imgs else None


# ─────────────────────────────────────────────────────────────
# 多模态抽取引擎（整合到 extract_engine 流程）
# ─────────────────────────────────────────────────────────────

class MultimodalExtractor:
    """
    多模态信息抽取引擎。
    给定原始页面（HTML + 图片 URL），提取文本和图片中的所有实体信息。
    """

    def __init__(self, llm_provider: str = "minimax", db_path: str | None = None):
        self.image_understander = ImageUnderstanding(llm_provider=llm_provider)
        self.standard_parser = StandardParser(llm_provider="volcano")
        self.db_path = db_path

    def enrich_event_from_images(
        self,
        event: dict[str, Any],
        html_content: str,
    ) -> dict[str, Any]:
        """
        给定一个已抽取的事件，检查页面中的产品图片，
        用视觉模型补充缺陷类型等信息。
        """
        main_img = extract_main_product_image(html_content)
        if not main_img:
            return event

        try:
            context = event.get("hazard_desc", "")[:300]
            img_result = self.image_understander.understand_from_url(main_img, context)

            event["image_defect_type"] = img_result.get("defect_type", "")
            event["image_risk_level"] = img_result.get("risk_level", "")
            event["image_description"] = img_result.get("description", "")
            event["image_hazard_signals"] = img_result.get("hazard_signals", [])
            event["image_confidence"] = img_result.get("confidence", 0.0)

            if img_result.get("risk_level") == "高" and event.get("severity_level") == "中等":
                event["severity_level"] = "高"
                event["severity_upgraded_by_image"] = True

            return event

        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            event["image_error"] = str(e)
            return event


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    img = ImageUnderstanding(llm_provider="minimax")
    print("图片理解模块初始化成功")
    print("  注意：实际使用需要有效的图片 URL")

    std = StandardParser(llm_provider="volcano")
    print("标准解析模块初始化成功")
    print("  注意：实际使用需要有效的 PDF 文件路径")
