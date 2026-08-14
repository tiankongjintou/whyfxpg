"""
AustraliaACCCAdapter — 澳大利亚竞争和消费者委员会（ACCC）产品安全召回数据适配器。

Australian Competition and Consumer Commission (ACCC) Product Safety Recalls.
数据来源：productsafety.gov.au 召回数据库 API。

参考：https://www.productsafety.gov.au/recalls
"""

import hashlib
import re
import time
from datetime import datetime
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class AustraliaACCCAdapter(BaseSourceAdapter):
    """
    ACCC 产品安全召回数据适配器。

    支持：
    - 英语召回数据（仅英文，ACCC 无官方双语 API）
    - 按时间范围过滤（since 参数）
    """

    source_id = "ACC"
    source_name = "Australian Competition and Consumer Commission - Product Safety Recalls"

    # ACCC Recalls API endpoint
    BASE_URL: ClassVar[str] = (
        "https://www.productsafety.gov.au/recalls/recall-search?term=&page="
    )

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html",
        "Accept-Language": "en-AU, en-US, en-GB, en */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 严重度映射（澳大利亚分类 → 统一标签）
    SEVERITY_MAP: ClassVar[dict[str, str]] = {
        "Serious": "严重",
        "Serious - Urgent": "严重",
        "Serious - Non-Urgent": "一般",
        "Non-serious": "轻微",
        "Minor": "轻微",
    }

    # 危害类型常用关键词（用于从文本中推断）
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "fire", "flame", "burn", "electrical", "shock", "choking",
        "toxic", "poison", "laceration", "fracture", "entrapment",
        "suffocation", "drowning", "chemical", "microbiological",
        "contamination", "defect", "breakdown", "fall", "crush",
        "burn hazard", "fire hazard", "electrical hazard", "carbon monoxide",
    ]

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "澳大利亚竞争和消费者委员会产品安全召回"

    def _health_url(self) -> str:
        return self.BASE_URL + "1"

    def health_check(self) -> bool:
        """检查 ACCC 产品安全网站是否可达。"""
        try:
            resp = self._session.get(self.BASE_URL + "1" + "&limit=1", timeout=self.TIMEOUT)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底，刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 ACCC 产品安全召回数据库抓取数据（仅英文）。
        """
        responses: list[SourceResponse] = []
        page = 1
        max_pages = 10
        cutoff = since.isoformat() if since else None

        while page <= max_pages:
            url = f"{self.BASE_URL}{page}&limit=50"
            try:
                resp = self._session.get(url, timeout=self.TIMEOUT)
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001 — 外部调用兜底，刻意吞异常
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

            data = self._parse_json_response(resp.content)
            if not data:
                break

            for item in data:
                source_resp = self._item_to_response(item)
                if cutoff and source_resp.published_at and source_resp.published_at < cutoff:
                    continue
                responses.append(source_resp)

            # 没有更多数据
            if len(data) < 50:
                break

            page += 1
            time.sleep(1)  # 礼貌限速

        return responses

    def _parse_json_response(self, content: bytes) -> list[dict[str, Any]]:
        """解析 JSON 响应。A CC API 返回 JSON 列表或包装结构。"""
        import json

        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # 可能是 { "results": [...] } 或 { "data": [...] } 结构
                for key in ("results", "data", "recalls", "items", "records"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                return [data]
            return []
        except json.JSONDecodeError:
            return []

    def _item_to_response(self, item: dict[str, Any]) -> SourceResponse:
        """将单个 API item 转换为 SourceResponse。"""
        title = self._extract_field(
            item, ["title", "name", "product_name", "recalling_firm", "Product name"]
        )
        raw_content = self._extract_field(
            item,
            [
                "raw_content",
                "description",
                "hazard_summary",
                "product",
                "Hazard description",
                "Product description",
                "Summary",
            ],
        )
        if isinstance(raw_content, str):
            raw_content_bytes = raw_content.encode("utf-8")
        elif isinstance(raw_content, bytes):
            raw_content_bytes = raw_content
        else:
            raw_content_bytes = str(raw_content).encode("utf-8")

        published_at = self._extract_date(item)
        severity = self._extract_severity(item)
        hazard_type = self._extract_hazard(item, raw_content_bytes)
        country = self._extract_country(item)
        manufacturer = self._extract_manufacturer(item)
        product_name = self._extract_product(item)
        url = self._extract_url(item)

        return SourceResponse(
            source_id=self.source_id,
            url=url or "",
            raw_content=raw_content_bytes,
            title=title or "",
            published_at=published_at,
            country=country,
            language="en",
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

    def _extract_date(self, item: dict[str, Any]) -> str | None:
        """提取发布日期。"""
        date_fields = [
            "date_published",
            "published_date",
            "recall_date",
            "date",
            "created_at",
            "Date published",
            "Published date",
            "Recall date",
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
        # 数字格式
        m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", value)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return None

    def _extract_severity(self, item: dict[str, Any]) -> str:
        """提取严重度等级。"""
        sev = (
            item.get("severity", "")
            or item.get("risk_level", "")
            or item.get("type", "")
            or item.get("Classification", "")
            or item.get("Risk classification", "")
        )
        if not sev:
            return "一般"
        sev_lower = sev.lower()
        return self.SEVERITY_MAP.get(sev, self.SEVERITY_MAP.get(sev_lower, "一般"))

    def _extract_hazard(
        self, item: dict[str, Any], raw_content: bytes
    ) -> str:
        """从 item 或 raw_content 中推断危害类型。"""
        hazard = (
            item.get("hazard_type", "")
            or item.get("hazard", "")
            or item.get("risk", "")
            or item.get("Hazard type", "")
            or item.get("Risk", "")
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
        """提取原产国。ACCC 数据中原产国通常是 AU（澳大利亚）或进口国。"""
        country = item.get("country", "") or item.get("origin_country", "") or item.get("Country", "")
        if country:
            return country[:2].upper()
        return "AU"

    def _extract_manufacturer(self, item: dict[str, Any]) -> str:
        """提取制造商/召回方。"""
        return (
            item.get("manufacturer", "")
            or item.get("recalling_firm", "")
            or item.get("company", "")
            or item.get("firm", "")
            or item.get("Supplier", "")
            or item.get("Trader", "")
        ).strip()

    def _extract_product(self, item: dict[str, Any]) -> str:
        """提取产品名称。"""
        return (
            item.get("product", "")
            or item.get("product_name", "")
            or item.get("description", "")
            or item.get("name", "")
            or item.get("Product name", "")
        ).strip()

    def _extract_url(self, item: dict[str, Any]) -> str:
        """提取详情页 URL。"""
        url = item.get("url", "") or item.get("link", "") or item.get("href", "")
        if url and not url.startswith("http"):
            url = "https://www.productsafety.gov.au" + url
        return url

    def _dedup_key(self, resp: SourceResponse) -> str:
        """生成去重键：基于标题+制造商的 hash。"""
        sig = f"{resp.title}|{resp.manufacturer}".encode()
        return hashlib.sha256(sig).hexdigest()[:16]

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
            "country": raw.country or "AU",
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
            "电子产品": ["electronic", "battery", "charger", "lamp", "led", "wire", "cable", "adapter"],
            "儿童用品": ["child", "infant", "baby", "toy", "crib", "stroller", "car seat", "bottle"],
            "食品": ["food", "meat", "dairy", "organic", "contaminant", "bacterial", "food"],
            "化妆品": ["cosmetic", "skin", "cream", "lotion", "beauty"],
            "药品": ["drug", "pharmaceutical", "medicine", "tablet", "capsule"],
            "医疗器械": ["medical", "device", "implant", "diagnostic", "hospital"],
            "家用电器": ["appliance", "kitchen", "heater", "fan", "motor", "pump", "vacuum"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
