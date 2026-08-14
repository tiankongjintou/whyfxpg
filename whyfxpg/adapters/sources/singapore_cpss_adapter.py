"""
SingaporeCPSSAdapter — 新加坡消费者保护局（Consumer Protection & Safety Branch）数据源适配器。

数据来源：Enterprise Singapore / CPSS 安全预警页面。
https://www.enterprise.gov.sg/en/consumers/safety-alerts

参考：新加坡消费品安全法规（CPSR）和 CPSS 官方召回公告。
"""

import re
from datetime import datetime, timezone
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class SingaporeCPSSAdapter(BaseSourceAdapter):
    """
    新加坡消费者保护局（CPSS）消费品安全预警数据适配器。

    支持：
    - 英文消费品安全预警数据
    - 按时间范围过滤（since 参数）
    """

    source_id = "SINGAPORE_CPSS"
    source_name = "Singapore Consumer Protection (CPSS)"

    BASE_URL: ClassVar[str] = "https://www.enterprise.gov.sg/en/consumers/safety-alerts"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html, application/xhtml+xml, */*",
        "Accept-Language": "en-SG, en-US, en, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 危害类型关键词
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "fire", "burn", "electrical", "shock", "choking", "toxic",
        "laceration", "fracture", "entrapment", "suffocation",
        "chemical", "microbiological", "contamination", "defect",
        "collapse", "tip-over", "strangulation", "drowning",
    ]

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "新加坡消费者保护局（CPSS）"

    def _health_url(self) -> str:
        return self.BASE_URL

    def health_check(self) -> bool:
        """检查 CPSS 页面是否可达。"""
        try:
            resp = self._session.get(self.BASE_URL, timeout=self.TIMEOUT)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 CPSS 安全预警页面抓取数据。
        """
        responses: list[SourceResponse] = []
        cutoff = since.isoformat() if since else None

        try:
            resp = self._session.get(self.BASE_URL, timeout=self.TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            responses.append(
                SourceResponse(
                    source_id=self.source_id,
                    url=self.BASE_URL,
                    raw_content=b"",
                    status="error",
                    error_msg=f"fetch failed: {exc!s}",
                    language="en",
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
                    country="SG",
                    language="en",
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
        import html as html_module

        try:
            text = html.decode("utf-8", errors="ignore")
        except UnicodeDecodeError:
            text = html.decode("latin-1", errors="ignore")

        items: list[dict[str, Any]] = []

        # 尝试提取 article / alert div 条目
        article_pattern = re.compile(
            r"<article[^>]*>(.*?)</article>", re.DOTALL | re.IGNORECASE
        )
        alert_pattern = re.compile(
            r"<div[^>]*class=\"[^\"]*(?:alert|safety|recall)[^\"]*\"[^>]*>(.*?)</div>",
            re.DOTALL | re.IGNORECASE,
        )

        for pattern in [article_pattern, alert_pattern]:
            for match in pattern.finditer(text):
                block = match.group(1)
                item = self._extract_item(block)
                if item.get("title"):
                    items.append(item)

        # 如果正则没有结果，尝试标题+日期模式
        if not items:
            title_date_pattern = re.compile(
                r"<h[23][^>]*>\s*([^<]+)\s*</h[23][^>]*>.*?"
                r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})",
                re.DOTALL | re.IGNORECASE,
            )
            for match in title_date_pattern.finditer(text[:50000]):
                title = match.group(1).strip()
                date_str = match.group(2).strip()
                if title and len(title) > 5:
                    items.append({
                        "title": html_module.unescape(title),
                        "published_at": self._normalize_date(date_str),
                        "raw_content": match.group(0).encode("utf-8"),
                    })

        return items

    def _extract_item(self, block: str) -> dict[str, Any]:
        """从 HTML 块中提取单个预警条目。"""
        import html as html_module

        # 提取标题
        title_match = re.search(r"<h[23][^>]*>\s*([^<]+)\s*</h[23]>", block, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""

        # 提取日期
        date_match = re.search(
            r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            block,
        )
        date_str = date_match.group(1) if date_match else ""

        # 提取 URL
        url_match = re.search(
            r"href=[\"']([^\"']+)[\"']", block, re.IGNORECASE
        )
        url = url_match.group(1) if url_match else ""
        if url and not url.startswith("http"):
            url = "https://www.enterprise.gov.sg" + url

        # 提取产品名/制造商
        product_match = re.search(
            r"(?:product|item)[^<]*?:\s*<[^>]*>\s*([^<]+)", block, re.IGNORECASE
        )
        product_name = product_match.group(1).strip() if product_match else ""

        manufacturer_match = re.search(
            r"(?:firm|company|manufacturer|recaller)[^<]*?:\s*<[^>]*>\s*([^<]+)",
            block, re.IGNORECASE
        )
        manufacturer = manufacturer_match.group(1).strip() if manufacturer_match else ""

        # 推断危害类型
        hazard_type = self._infer_hazard(block)
        severity = "一般"
        if any(kw in block.lower() for kw in ["death", "serious", "fatal", "critical"]):
            severity = "严重"
        elif any(kw in block.lower() for kw in ["minor", "moderate", "low"]):
            severity = "轻微"

        return {
            "title": html_module.unescape(title),
            "published_at": self._normalize_date(date_str),
            "url": url,
            "product_name": html_module.unescape(product_name),
            "manufacturer": html_module.unescape(manufacturer),
            "hazard_type": hazard_type,
            "severity": severity,
            "raw_content": block.encode("utf-8") if isinstance(block, str) else block,
        }

    def _infer_hazard(self, text: str) -> str:
        """从文本中推断危害类型。"""
        text_lower = text.lower()
        for kw in self.HAZARD_KEYWORDS:
            if kw in text_lower:
                return kw.capitalize()
        return "组合危险"

    def _normalize_date(self, value: str) -> str:
        """将各种日期格式归一化为 YYYY-MM-DD。"""
        if not value:
            return ""
        # 数字格式 DD/MM/YYYY 或 YYYY/MM/DD
        m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", value)
        if m:
            d, mo, yr = m.groups()
            yr = yr if len(yr) == 4 else f"20{yr}"
            return f"{yr}-{int(mo):02d}-{int(d):02d}"
        # ISO 格式 YYYY-MM-DD
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
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
            "country": raw.country or "SG",
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
            "电子产品": ["electronic", "battery", "charger", "lamp", "led", "wire", "cable", "adapter"],
            "儿童用品": ["child", "infant", "baby", "toy", "crib", "stroller", "car seat"],
            "食品": ["food", "meat", "dairy", "contaminant", "bacterial", "food"],
            "化妆品": ["cosmetic", "skin", "cream", "lotion", "beauty"],
            "药品": ["drug", "pharmaceutical", "medicine", "tablet", "capsule"],
            "医疗器械": ["medical", "device", "implant", "diagnostic", "hospital"],
            "家用电器": ["appliance", "kitchen", "heater", "fan", "motor", "pump", "vacuum"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
