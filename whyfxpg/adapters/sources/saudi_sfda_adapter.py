"""
SaudiSFDAAdapter — 沙特阿拉伯食品药品监督管理局（Saudi FDA / الهيئة العامة للغذاء والدواء）数据源适配器。

支持阿拉伯语/英语双语。
数据来源：Saudi FDA 官网安全预警 / 召回通知页面。

参考：https://www.sfda.gov.sa（沙特食品药品监督管理局）
"""

import re
from datetime import datetime, timezone
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class SaudiSFDAAdapter(BaseSourceAdapter):
    """
    沙特阿拉伯食品药品监督管理局（Saudi FDA）安全预警数据适配器。

    支持：
    - 阿拉伯语安全预警
    - 英语摘要（双语模式）
    - 按时间范围过滤（since 参数）
    """

    source_id = "SAUDI_SFDA"
    source_name = "Saudi FDA - Saudi Food and Drug Authority (الهيئة العامة للغذاء والدواء)"

    # Saudi FDA 安全预警 API / 页面
    BASE_URL: ClassVar[str] = "https://www.sfda.gov.sa"
    SAFETY_PATH: ClassVar[str] = "/en/consumers/safetyalerts"
    HEALTH_CHECK_URL: ClassVar[str] = BASE_URL + SAFETY_PATH

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html, application/xhtml+xml, */*",
        "Accept-Language": "ar, en-US, en, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 危害类型关键词（阿拉伯文 + 英文）
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "حريق", "fire", "burn",
        "صعق", "electrical", "shock",
        "اختناق", "choking", "suffocation",
        "تسمم", "toxic", "poison",
        "إصابة", "injury", "laceration", "fracture",
        "كيميائي", "chemical",
        "تلوث", "contamination",
        "عيب", "defect",
        "انهيار", "collapse",
    ]

    # 严重度映射
    SEVERITY_MAP: ClassVar[dict[str, str]] = {
        "خطر": "严重",
        "تحذير": "一般",
        "معلومة": "轻微",
        "danger": "严重",
        "warning": "一般",
        "information": "轻微",
        "critical": "严重",
        "major": "一般",
        "minor": "轻微",
    }

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "沙特食品药品监督管理局（Saudi FDA）"

    def _health_url(self) -> str:
        return self.HEALTH_CHECK_URL

    def health_check(self) -> bool:
        """检查 Saudi FDA 页面是否可达。"""
        try:
            resp = self._session.get(self.HEALTH_CHECK_URL, timeout=self.TIMEOUT)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 Saudi FDA 安全预警页面抓取数据。
        """
        responses: list[SourceResponse] = []
        cutoff = since.isoformat() if since else None

        try:
            resp = self._session.get(self.HEALTH_CHECK_URL, timeout=self.TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            responses.append(
                SourceResponse(
                    source_id=self.source_id,
                    url=self.HEALTH_CHECK_URL,
                    raw_content=b"",
                    status="error",
                    error_msg=f"fetch failed: {exc!s}",
                    language="ar",
                )
            )
            return responses

        html = resp.content
        items = self._parse_html(html)

        for item in items:
            published_at = item.get("published_at", "")
            if cutoff and published_at and published_at < cutoff:
                continue
            responses.append(
                SourceResponse(
                    source_id=self.source_id,
                    url=item.get("url", self.BASE_URL),
                    raw_content=item.get("raw_content", b""),
                    title=item.get("title", ""),
                    published_at=published_at,
                    country="SA",
                    language=item.get("language", "ar"),
                    hazard_type=item.get("hazard_type", ""),
                    severity=item.get("severity", "一般"),
                    product_name=item.get("product_name", ""),
                    manufacturer=item.get("manufacturer", ""),
                    raw_fields=item,
                    status="ok",
                )
            )

        return responses

    def _parse_html(self, html: bytes) -> list[dict[str, Any]]:
        """解析 HTML 页面，提取安全预警条目。"""
        # 尝试 UTF-8，然后 Arabic Windows 编码
        text = html.decode("utf-8", errors="ignore")

        items: list[dict[str, Any]] = []

        # 结构1: article 标签
        for block in re.finditer(
            r"<article[^>]*>(.*?)</article>", text, re.DOTALL | re.IGNORECASE
        ):
            item = self._extract_item(block.group(1))
            if item.get("title"):
                items.append(item)

        # 结构2: div.alert / div.recall / div.safety 类
        if not items:
            for block in re.finditer(
                r"<div[^>]*class=\"[^\"]*(?:alert|safety|recall|warning)[^\"]*\"[^>]*>(.*?)</div>",
                text, re.DOTALL | re.IGNORECASE
            ):
                item = self._extract_item(block.group(1))
                if item.get("title"):
                    items.append(item)

        # 结构3: table rows
        if not items:
            for block in re.finditer(
                r"<tr[^>]*>(.*?)</tr>", text, re.DOTALL | re.IGNORECASE
            ):
                item = self._extract_item(block.group(1))
                if item.get("title"):
                    items.append(item)

        return items

    def _extract_item(self, block: str) -> dict[str, Any]:
        """从 HTML 块中提取单个预警条目。"""
        import html as html_module

        # 提取标题（支持 Arabic + English）
        title_match = re.search(
            r"<h[1-4][^>]*>\s*([^<]+?)\s*</h[1-4]>", block, re.IGNORECASE
        )
        if not title_match:
            title_match = re.search(
                r"<td[^>]*>\s*([^<]{5,200})\s*</td>", block, re.IGNORECASE
            )
        title = title_match.group(1).strip() if title_match else ""
        title = re.sub(r"<[^>]+>", "", title).strip()

        # 提取日期
        date_match = re.search(
            r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})",
            block,
        )
        date_str = date_match.group(1) if date_match else ""

        # 提取 URL
        url_match = re.search(
            r"href=[\"']([^\"']+)[\"']", block, re.IGNORECASE
        )
        url = url_match.group(1) if url_match else ""
        if url and not url.startswith("http"):
            url = self.BASE_URL + url

        # 提取产品名
        product_match = re.search(
            r"(?:product|منتج|item)[^<]*?[:\s]*([^\n<]{3,100})",
            block, re.IGNORECASE
        )
        product_name = product_match.group(1).strip() if product_match else ""

        # 提取制造商
        firm_match = re.search(
            r"(?:manufacturer|company|شركة|الشركة)[^<]*?[:\s]*([^\n<]{3,100})",
            block, re.IGNORECASE
        )
        manufacturer = firm_match.group(1).strip() if firm_match else ""

        # 推断危害类型
        hazard_type = self._infer_hazard(block)

        # 推断严重度
        severity = self._infer_severity(block)

        # 判断语言（是否含阿拉伯文）
        has_arabic = bool(re.search(r"[\u0600-\u06FF]", title))
        language = "ar" if has_arabic else "en"

        return {
            "title": html_module.unescape(title),
            "published_at": self._normalize_date(date_str),
            "url": url,
            "product_name": html_module.unescape(product_name),
            "manufacturer": html_module.unescape(manufacturer),
            "hazard_type": hazard_type,
            "severity": severity,
            "language": language,
            "raw_content": block.encode("utf-8") if isinstance(block, str) else block,
        }

    def _infer_hazard(self, text: str) -> str:
        """从文本中推断危害类型（阿拉伯文+英文）。"""
        text_lower = text.lower()
        hazard_map = {
            "حريق": "火灾", "fire": "fire",
            "صعق": "触电", "electrical": "electrical",
            "اختناق": "窒息", "choking": "choking",
            "تسمم": "中毒", "toxic": "toxic",
            "إصابة": "伤害", "injury": "injury",
            "كيميائي": "化学危险", "chemical": "chemical",
            "تلوث": "污染", "contamination": "contamination",
            "عيب": "产品缺陷", "defect": "defect",
            "انهيار": "坍塌", "collapse": "collapse",
        }
        for kw, label in hazard_map.items():
            if kw.lower() in text_lower:
                return label
        return "组合危险"

    def _infer_severity(self, text: str) -> str:
        """推断严重度等级。"""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["خطر", "danger", "critical"]):
            return "严重"
        if any(kw in text_lower for kw in ["تحذير", "warning", "major"]):
            return "一般"
        if any(kw in text_lower for kw in ["معلومة", "information", "minor"]):
            return "轻微"
        return "一般"

    def _normalize_date(self, value: str) -> str:
        """将各种日期格式归一化为 YYYY-MM-DD。"""
        if not value:
            return ""
        # YYYY-MM-DD
        m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        # DD-MM-YYYY or MM-DD-YYYY
        m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", value)
        if m:
            # 阿拉伯地区通常 DD/MM/YYYY
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        return value.strip()

    def parse(self, raw: SourceResponse) -> dict[str, Any]:
        """
        将 SourceResponse 解析为符合 risk_events 表契约的字典。
        """
        text = raw.raw_content
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="ignore")
        text_clean = re.sub(r"<[^>]+>", " ", str(text))
        text_clean = re.sub(r"\s+", " ", text_clean)

        return {
            "source_id": self.source_id,
            "source_url": raw.url,
            "title": raw.title or raw.url,
            "product_name": raw.product_name,
            "brand": "",
            "model": "",
            "hs_code": "",
            "product_category": self._infer_category(text_clean),
            "country": raw.country or "SA",
            "manufacturer": raw.manufacturer,
            "hazard_type": raw.hazard_type or "组合危险",
            "hazard_desc": text_clean[:500],
            "severity_level": raw.severity or "一般",
            "ss_score": None,
            "probability_level": "",
            "ps_score": None,
            "country_factor": None,
            "product_factor": None,
            "history_factor": None,
            "evidence_factor": None,
            "total_score": None,
            "rs_level": None,
            "standards": "",
            "original_text": text,
            "publish_date": raw.published_at or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "evaluated_at": None,
            "config_version": "",
            "model_version": "",
            "extraction_confidence": 0.6,
            "review_status": "auto",
            "extracted_language": raw.language,
        }

    def _infer_category(self, text: str) -> str:
        """根据文本内容推断产品类别。"""
        text_lower = text.lower()
        category_keywords = {
            "电子产品": ["electronic", "battery", "charger", "lamp", "cable", "جهاز إلكتروني"],
            "儿童用品": ["child", "infant", "baby", "toy", "crib", "أطفال"],
            "食品": ["food", "meat", "dairy", "contaminant", "غذاء", "طعام"],
            "化妆品": ["cosmetic", "beauty", "skin", "makeup", "مستحضر"],
            "药品": ["drug", "pharmaceutical", "medicine", "drug", "دواء"],
            "医疗器械": ["medical", "device", "hospital", "device", "جهاز طبي"],
            "家用电器": ["appliance", "kitchen", "heater", "fan", "motor", "جهاز منزلي"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
