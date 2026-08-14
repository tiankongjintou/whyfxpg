"""
IndiaBISAdapter — 印度 BIS CRS（Bureau of Indian Standards - Conformity Assessment Regulation）数据源适配器。

数据来源：BIS CRS 官方数据库 (bis.gov.in)
语言：英语

参考：https://bis.gov.in/index.php/products/conformity-assessment-scheme/crs-recall/
"""

import hashlib
import re
import time
from datetime import datetime
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class IndiaBISAdapter(BaseSourceAdapter):
    """
    印度 BIS CRS 召回数据适配器。

    支持：
    - 英语召回数据（default）
    - 按时间范围过滤（since 参数）
    - PDF 和 HTML 格式处理
    """

    source_id = "INDIA_BIS"
    source_name = "Bureau of Indian Standards - Conformity Assessment Regulation"

    # BIS CRS recall/search page
    BASE_URL: ClassVar[str] = "https://bis.gov.in/index.php/products/conformity-assessment-scheme/crs-recall/"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-IN, en-US, en-GB, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 严重度映射（印度 BIS 标准）
    SEVERITY_MAP: ClassVar[dict[str, str]] = {
        "Type I": "严重",
        "Type II": "一般",
        "Type III": "轻微",
        "Category I": "严重",
        "Category II": "一般",
        "Category III": "轻微",
    }

    # 危害类型常用关键词
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "fire", "flame", "burn", "electrical", "shock", "choking",
        "toxic", "poison", "laceration", "fracture", "entrapment",
        "suffocation", "drowning", "chemical", "microbiological",
        "contamination", "defect", "breakdown", "short circuit",
        "overheating", "explosion", "injury", "hazard",
    ]

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "印度 BIS 标准符合性评定数据库"

    def _health_url(self) -> str:
        return self.BASE_URL

    def health_check(self) -> bool:
        """检查 BIS CRS 网站是否可达。"""
        try:
            resp = self._session.get(self.BASE_URL, timeout=self.TIMEOUT)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 BIS CRS 数据库抓取数据。

        尝试 JSON API 格式，fallback 到 HTML 列表解析。
        """
        # 优先尝试 JSON API
        responses = self._fetch_json(since)
        if responses:
            return responses

        # Fallback 到 HTML 页面解析
        return self._fetch_html(since)

    def _fetch_json(self, since: datetime | None = None) -> list[SourceResponse]:
        """尝试抓取 JSON 格式数据（BIS 可能提供 API）。"""
        # BIS CRS 可能提供 API endpoint，这里尝试常见模式
        api_urls = [
            "https://bis.gov.in/wp-content/uploads/crs-recall-data.json",
            "https://bis.gov.in/api/recalls",
        ]

        for api_url in api_urls:
            try:
                resp = self._session.get(api_url, timeout=self.TIMEOUT)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if isinstance(data, list):
                    return self._parse_json_items(data, since)
                if isinstance(data, dict):
                    for key in ("results", "data", "recalls", "items"):
                        if key in data and isinstance(data[key], list):
                            return self._parse_json_items(data[key], since)
            except Exception:  # noqa: BLE001, S112 — 外部调用兜底,刻意吞异常
                continue

        return []

    def _parse_json_items(
        self, items: list[dict[str, Any]], since: datetime | None = None
    ) -> list[SourceResponse]:
        """解析 JSON 格式的召回数据。"""
        responses: list[SourceResponse] = []
        cutoff = since.isoformat() if since else None

        for item in items:
            source_resp = self._item_to_response(item, "en")
            if cutoff and source_resp.published_at and source_resp.published_at < cutoff:
                continue
            responses.append(source_resp)

        return responses

    def _fetch_html(self, since: datetime | None = None) -> list[SourceResponse]:
        """抓取并解析 HTML 页面格式的数据。"""
        responses: list[SourceResponse] = []
        page = 1
        max_pages = 10
        cutoff = since.isoformat() if since else None

        while page <= max_pages:
            url = f"{self.BASE_URL}?page={page}"
            try:
                resp = self._session.get(url, timeout=self.TIMEOUT)
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
                responses.append(
                    SourceResponse(
                        source_id=self.source_id,
                        url=url,
                        raw_content=b"",
                        status="error",
                        error_msg=f"fetch failed: {exc!s}",
                        language="en",
                    )
                )
                break

            items = self._parse_html_items(resp.text)
            if not items:
                break

            for item in items:
                source_resp = self._item_to_response(item, "en")
                if cutoff and source_resp.published_at and source_resp.published_at < cutoff:
                    continue
                responses.append(source_resp)

            page += 1
            time.sleep(1)  # 礼貌限速

        return responses

    def _parse_html_items(self, html: str) -> list[dict[str, Any]]:
        """解析 HTML 页面中的召回条目。"""
        items: list[dict[str, Any]] = []

        # 尝试提取表格行
        table_pattern = re.compile(
            r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?</tr>',
            re.DOTALL | re.IGNORECASE,
        )

        for row_match in table_pattern.finditer(html):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_match.group(0), re.DOTALL)
            if len(cells) >= 3:
                item: dict[str, Any] = {}
                # 尝试从单元格提取信息
                for i, cell in enumerate(cells):
                    clean_cell = re.sub(r'<[^>]+>', ' ', cell).strip()
                    if i == 0:
                        item['date'] = clean_cell
                    elif i == 1:
                        item['product'] = clean_cell
                    elif i == 2:
                        item['manufacturer'] = clean_cell
                    elif i == 3:
                        item['hazard'] = clean_cell
                items.append(item)

        # 尝试提取列表项
        if not items:
            list_pattern = re.compile(
                r'<li[^>]*class=["\']recall-item["\'][^>]*>(.*?)</li>',
                re.DOTALL | re.IGNORECASE,
            )
            for li_match in list_pattern.finditer(html):
                text = re.sub(r'<[^>]+>', ' ', li_match.group(1)).strip()
                if text:
                    items.append({'text': text, 'raw': li_match.group(1)})

        return items

    def _item_to_response(self, item: dict[str, Any], lang: str) -> SourceResponse:
        """将单个 item 转换为 SourceResponse。"""
        title = self._extract_field(
            item, ["title", "product", "name", "product_name", "recalling_firm"]
        )
        raw_content = self._extract_field(
            item, ["raw_content", "description", "hazard_summary", "text", "raw"]
        )
        if isinstance(raw_content, str):
            raw_content = raw_content.encode("utf-8")
        elif not isinstance(raw_content, bytes):
            raw_content = str(raw_content).encode("utf-8")

        published_at = self._extract_date(item, lang)
        severity = self._extract_severity(item, lang)
        hazard_type = self._extract_hazard(item, raw_content, lang)
        country = self._extract_country(item)
        manufacturer = self._extract_manufacturer(item)
        product_name = self._extract_product(item)
        url = self._extract_url(item)

        return SourceResponse(
            source_id=self.source_id,
            url=url or "",
            raw_content=raw_content,
            title=title or "",
            published_at=published_at,
            country=country,
            language=lang,
            hazard_type=hazard_type,
            severity=severity,
            product_name=product_name or "",
            manufacturer=manufacturer or "",
            raw_fields=dict(item),
            status="ok",
        )

    def _extract_field(self, item: dict[str, Any], keys: list[str]) -> str:
        """从 item 中按优先级查找字段。"""
        for key in keys:
            val = item.get(key, "")
            if val:
                return str(val).strip()
        return ""

    def _extract_date(self, item: dict[str, Any], lang: str) -> str | None:
        """提取发布日期。"""
        date_fields = [
            "date", "date_published", "published_date", "recall_date",
            "created_at", "modified", "updated",
        ]
        for f in date_fields:
            val = item.get(f, "")
            if val:
                normalized = self._normalize_date(str(val))
                if normalized:
                    return normalized
        return None

    def _normalize_date(self, value: str) -> str | None:
        """将各种日期格式归一化为 YYYY-MM-DD。"""
        # ISO 格式
        m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
        if m:
            return m.group(1)
        # DD-MM-YYYY 格式（印度常用）
        m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})", value)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        # YYYY/MM/DD 格式
        m = re.match(r"(\d{4})/(\d{2})/(\d{2})", value)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        # 中文格式
        m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return None

    def _extract_severity(self, item: dict[str, Any], lang: str) -> str:
        """提取严重度等级。"""
        sev_str = (
            item.get("severity", "")
            or item.get("risk_level", "")
            or item.get("type", "")
            or item.get("category", "")
        )
        return self.SEVERITY_MAP.get(sev_str, sev_str or "一般")

    def _extract_hazard(
        self, item: dict[str, Any], raw_content: bytes, lang: str
    ) -> str:
        """从 item 或 raw_content 中推断危害类型。"""
        hazard = (
            item.get("hazard_type", "")
            or item.get("hazard", "")
            or item.get("risk", "")
            or item.get("danger", "")
        )
        if hazard:
            return hazard.strip()

        # 从 raw_content 中检测关键词
        text = raw_content.decode("utf-8", errors="ignore").lower()
        for kw in self.HAZARD_KEYWORDS:
            if kw in text:
                return kw.capitalize()
        return "组合危险"

    def _extract_country(self, item: dict[str, Any]) -> str:
        """提取原产国。印度 BIS 数据中原产国通常是 IN（印度）。"""
        country = item.get("country", "") or item.get("origin_country", "")
        if country:
            return country[:2].upper()
        return "IN"

    def _extract_manufacturer(self, item: dict[str, Any]) -> str:
        """提取制造商/召回方。"""
        return (
            item.get("manufacturer", "")
            or item.get("recalling_firm", "")
            or item.get("company", "")
            or item.get("firm", "")
            or item.get("brand", "")
        ).strip()

    def _extract_product(self, item: dict[str, Any]) -> str:
        """提取产品名称。"""
        return (
            item.get("product", "")
            or item.get("product_name", "")
            or item.get("description", "")
            or item.get("name", "")
        ).strip()

    def _extract_url(self, item: dict[str, Any]) -> str:
        """提取详情页 URL。"""
        url = item.get("url", "") or item.get("link", "") or item.get("href", "")
        if url and not url.startswith("http"):
            url = "https://bis.gov.in" + url
        return url

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
        - country → country
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
            "country": raw.country or "IN",
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
            "publish_date": raw.published_at or datetime.now().strftime("%Y-%m-%d"),  # noqa: DTZ005
            "extracted_at": datetime.now().isoformat(),  # noqa: DTZ005
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
            "电子产品": ["electronic", "battery", "charger", "lamp", "led", "wire", "cable", "circuit"],
            "儿童用品": ["child", "infant", "baby", "toy", "crib", "stroller", "car seat"],
            "食品": ["food", "meat", "dairy", "organic", "contaminant", "bacterial"],
            "化妆品": ["cosmetic", "skin", "cream", "lotion", "beauty"],
            "药品": ["drug", "pharmaceutical", "medicine", "tablet", "capsule"],
            "医疗器械": ["medical", "device", "implant", "diagnostic", "hospital"],
            "家用电器": ["appliance", "kitchen", "heater", "fan", "motor", "pump"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
