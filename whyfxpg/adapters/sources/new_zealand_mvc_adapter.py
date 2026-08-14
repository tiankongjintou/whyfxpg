"""
NewZealandMVCAdapter — 新西兰商务、创新和就业部（Ministry of Business, Innovation and Employment）
消费者保护（Consumer Protection）数据源适配器。

数据来源：MBIE 消费者产品安全页面 + Consumer Protection (Commerce Commission) 召回数据库。
https://www.mbie.govt.nz/business-and-employment/consumer/consumer-product-safety/
https://www.consumerprotection.govt.nz/
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class NewZealandMVCAdapter(BaseSourceAdapter):
    """
    新西兰消费者产品安全数据适配器（MBIE Consumer Protection / Commerce Commission）。

    支持：
    - 英语召回/预警数据（default）
    - 按时间范围过滤（since 参数）
    """

    source_id = "NZ_MVCI"
    source_name = "New Zealand MBIE Consumer Protection"

    # MBIE Consumer Product Safety 页面（主数据源）
    BASE_URL: ClassVar[str] = "https://www.mbie.govt.nz/business-and-employment/consumer/consumer-product-safety/"

    # Commerce Commission Consumer Protection 召回页面（备用数据源）
    CONSUMER_PROTECTION_URL: ClassVar[str] = "https://www.consumerprotection.govt.nz/"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html, application/json, */*",
        "Accept-Language": "en-NZ, en-US, en, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 严重度映射（英文 → 统一标签）
    SEVERITY_MAP: ClassVar[dict[str, str]] = {
        "type i": "严重",
        "type ii": "一般",
        "type iii": "轻微",
        "type 1": "严重",
        "type 2": "一般",
        "type 3": "轻微",
        "serious": "严重",
        "moderate": "一般",
        "minor": "轻微",
        "critical": "严重",
        "high": "严重",
        "medium": "一般",
        "low": "轻微",
    }

    # 危害类型常用关键词
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "fire", "flame", "burn", "electrical", "shock", "choking",
        "toxic", "poison", "laceration", "fracture", "entrapment",
        "suffocation", "drowning", "chemical", "microbiological",
        "contamination", "defect", "breakdown", "collapse",
        "tip-over", "strangulation", "asphyxiation", "injury",
    ]

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "新西兰商务、创新和就业部消费者保护（MBIE）"

    def _health_url(self) -> str:
        return self.BASE_URL

    def health_check(self) -> bool:
        """检查 MBIE 消费者产品安全页面是否可达。"""
        try:
            resp = self._session.get(self.BASE_URL, timeout=self.TIMEOUT)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 MBIE 消费者产品安全页面抓取数据。

        依次尝试：
        1. MBIE 主页面（HTML 页面解析）
        2. Consumer Protection 页面（备用）
        """
        responses: list[SourceResponse] = []

        # 尝试主 MBIE 页面
        mbie_responses = self._fetch_mbie(since)
        responses.extend(mbie_responses)

        # 按 raw_content hash 去重
        seen: dict[str, SourceResponse] = {}
        for resp in responses:
            key = self._dedup_key(resp)
            if key not in seen:
                seen[key] = resp

        return list(seen.values())

    def _fetch_mbie(self, since: datetime | None = None) -> list[SourceResponse]:
        """从 MBIE 主页面抓取数据。"""
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
                    country="NZ",
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
        """解析 MBIE HTML 页面，提取消费者产品安全条目。"""
        import html as html_module

        try:
            text = html.decode("utf-8", errors="ignore")
        except UnicodeDecodeError:
            text = html.decode("latin-1", errors="ignore")

        items: list[dict[str, Any]] = []

        # 尝试提取 article / alert / recall div 条目
        article_pattern = re.compile(
            r"<article[^>]*>(.*?)</article>", re.DOTALL | re.IGNORECASE
        )
        alert_pattern = re.compile(
            r"<div[^>]*class=\"[^\"]*(?:alert|safety|recall|product)[^\"]*\"[^>]*>(.*?)</div>",
            re.DOTALL | re.IGNORECASE,
        )
        list_item_pattern = re.compile(
            r"<li[^>]*class=\"[^\"]*(?:recall|alert|safety)[^\"]*\"[^>]*>(.*?)</li>",
            re.DOTALL | re.IGNORECASE,
        )

        for pattern in [article_pattern, alert_pattern, list_item_pattern]:
            for match in pattern.finditer(text):
                block = match.group(1)
                item = self._extract_item(block)
                if item.get("title"):
                    items.append(item)

        # 如果正则没有结果，尝试标题+日期模式
        if not items:
            title_date_pattern = re.compile(
                r"<h[23][^>]*>\s*([^<]+?)\s*</h[23][^>]*>.*?"
                r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})",
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
        title_match = re.search(r"<h[23][^>]*>\s*([^<]+?)\s*</h[23]>", block, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""

        # 提取日期
        date_match = re.search(
            r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})",
            block,
        )
        date_str = date_match.group(1) if date_match else ""

        # 提取 URL
        url_match = re.search(
            r"href=[\"']([^\"']+)[\"']", block, re.IGNORECASE
        )
        url = url_match.group(1) if url_match else ""
        if url and not url.startswith("http"):
            url = "https://www.mbie.govt.nz" + url

        # 提取产品名
        product_match = re.search(
            r"(?:product|item|product name|description)[^<]*?:\s*<[^>]*>\s*([^<<\n]+)",
            block, re.IGNORECASE
        )
        product_name = product_match.group(1).strip() if product_match else ""

        # 提取制造商/召回方
        manufacturer_match = re.search(
            r"(?:firm|company|manufacturer|recaller|supplier)[^<]*?:\s*<[^>]*>\s*([^<<\n]+)",
            block, re.IGNORECASE
        )
        manufacturer = manufacturer_match.group(1).strip() if manufacturer_match else ""

        # 如果还没有提取到产品名，尝试从标题中猜测
        if not product_name and title:
            product_name = self._extract_product_from_title(title)

        # 推断危害类型
        hazard_type = self._infer_hazard(block)
        severity = self._infer_severity(block)

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

    def _extract_product_from_title(self, title: str) -> str:
        """从标题中提取产品名称（辅助方法）。"""
        # 标题格式通常是 "Product Name - Hazard Description" 或 "Hazard Description - Product Name"
        separators = [" - ", " – ", " — ", " :: ", " | "]
        for sep in separators:
            if sep in title:
                parts = title.split(sep)
                if len(parts) >= 2:
                    # 假设较短的、不含 hazard 关键词的部分是产品名
                    for part in parts:
                        part = part.strip()
                        part_lower = part.lower()
                        if not any(kw in part_lower for kw in self.HAZARD_KEYWORDS) and len(part) > 3 and len(part) < 100:
                            return part
        return ""

    def _infer_hazard(self, text: str) -> str:
        """从文本中推断危害类型。"""
        text_lower = text.lower()
        for kw in self.HAZARD_KEYWORDS:
            if kw in text_lower:
                return kw.capitalize()
        return "组合危险"

    def _infer_severity(self, text: str) -> str:
        """从文本中推断严重度等级。"""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["death", "serious", "fatal", "critical", "type i", "type 1", "high risk"]):
            return "严重"
        if any(kw in text_lower for kw in ["moderate", "type ii", "type 2", "medium risk", "injury"]):
            return "一般"
        if any(kw in text_lower for kw in ["minor", "type iii", "type 3", "low risk"]):
            return "轻微"
        return "一般"

    def _normalize_date(self, value: str) -> str:
        """将各种日期格式归一化为 YYYY-MM-DD。"""
        if not value:
            return ""
        value = value.strip()

        # 英文月份格式：Jan 15, 2024 或 15 Jan 2024
        month_map = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12",
        }
        m = re.match(
            r"(?:(\d{1,2})\s+)?([A-Za-z]+)\s+(\d{4})",
            value,
        )
        if m:
            day = m.group(1) or "01"
            month_str = m.group(2).lower()[:3]
            year = m.group(3)
            month = month_map.get(month_str, "01")
            return f"{year}-{month}-{int(day):02d}"

        # 数字格式 DD/MM/YYYY 或 YYYY/MM/DD
        m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", value)
        if m:
            first, second, yr = m.groups()
            yr = yr if len(yr) == 4 else f"20{yr}"
            # 判断是 DD/MM/YYYY 还是 YYYY/MM/DD
            if int(first) > 12:
                # YYYY/MM/DD 格式
                return f"{yr}-{int(second):02d}-{int(first):02d}"
            else:
                # DD/MM/YYYY 格式（新西兰采用）
                return f"{yr}-{int(second):02d}-{int(first):02d}"

        # ISO 格式 YYYY-MM-DD
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        return value.strip()

    def _dedup_key(self, resp: SourceResponse) -> str:
        """生成去重键：基于标题+制造商的 hash。"""
        sig = f"{resp.title}|{resp.manufacturer}".encode()
        return hashlib.sha256(sig).hexdigest()[:16]

    def parse(self, raw: SourceResponse) -> dict[str, Any]:
        """
        将 SourceResponse 解析为符合 risk_events 表契约的字典。

        字段映射：
        - title → title
        - product_name → product_name
        - manufacturer → manufacturer
        - country → country（NZ）
        - hazard_type → hazard_type
        - severity → severity_level
        - raw_content → original_text
        - published_at → publish_date
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
            "country": raw.country or "NZ",
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
            "电子产品": [
                "electronic", "battery", "charger", "lamp", "led", "wire",
                "cable", "adapter", "power bank", "smartphone", "tablet",
            ],
            "儿童用品": [
                "child", "infant", "baby", "toy", "crib", "stroller",
                "car seat", "playpen", "high chair", "bottle",
            ],
            "食品": [
                "food", "meat", "dairy", "organic", "contaminant",
                "bacterial", "food product", "cosmetic", "dietary",
            ],
            "化妆品": [
                "cosmetic", "skin", "cream", "lotion", "beauty",
                "makeup", "hair product",
            ],
            "药品": [
                "drug", "pharmaceutical", "medicine", "tablet",
                "capsule", "prescription", "therapeutic",
            ],
            "医疗器械": [
                "medical", "device", "implant", "diagnostic",
                "hospital", "mask", "ppe", "ventilator",
            ],
            "家用电器": [
                "appliance", "kitchen", "heater", "fan", "motor",
                "pump", "vacuum", "air conditioner", "refrigerator",
            ],
            "家具": [
                "furniture", "chair", "table", "shelf", "cabinet",
                "wardrobe", "bed frame", "mattress",
            ],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
