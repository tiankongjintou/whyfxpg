"""
CanadaHealthAdapter — 加拿大卫生部（Health Canada）数据源适配器。

支持英文（en）和法文（fr）双语召回数据。
数据来源：Health Canada 召回数据库 API / RSS feed。

参考：https://healthcanada.gc.ca/recall-alert-rappels-api
"""

import hashlib
import re
import time
from datetime import datetime
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class CanadaHealthAdapter(BaseSourceAdapter):
    """
    加拿大卫生部召回数据适配器（Health Canada / Santé Canada）。

    支持：
    - 英语召回（default）
    - 法语召回（lang=fr）
    - 按时间范围过滤（since 参数）
    """

    source_id = "CANADA_HEALTH"
    source_name = "Health Canada - Product Recall Database"

    # Health Canada Recall Alert API endpoints
    BASE_URL_EN: ClassVar[str] = "https://healthcanada.gc.ca/recall-alert-rappels-api/search?"
    BASE_URL_FR: ClassVar[str] = "https://healthcanada.gc.ca/recall-alert-rappels-api/search?lang=fr&"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html",
        "Accept-Language": "en-CA, fr-CA, en-US, fr, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 严重度映射（英文 → 统一标签）
    SEVERITY_MAP_EN: ClassVar[dict[str, str]] = {
        "Type I": "严重",
        "Type II": "一般",
        "Type III": "轻微",
    }

    SEVERITY_MAP_FR: ClassVar[dict[str, str]] = {
        "type I": "严重",
        "type II": "一般",
        "type iii": "轻微",
    }

    # 危害类型常用关键词
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "fire", "flame", "burn", "electrical", "shock", "choking",
        "toxic", "poison", "laceration", "fracture", "entrapment",
        "suffocation", "drowning", "chemical", "microbiological",
        "contamination", "defect", "breakdown",
    ]

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "加拿大卫生部召回数据库"

    def _health_url(self) -> str:
        return self.BASE_URL_EN

    def health_check(self) -> bool:
        """检查 Health Canada API 是否可达。"""
        try:
            resp = self._session.get(
                self.BASE_URL_EN + "limit=1",
                timeout=self.TIMEOUT,
            )
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 Health Canada 召回数据库抓取数据。

        同时抓取英文和法文数据，合并去重。
        """
        responses: list[SourceResponse] = []

        # 英文数据
        en_responses = self._fetch_lang("en", since)
        responses.extend(en_responses)

        # 法文数据
        fr_responses = self._fetch_lang("fr", since)
        responses.extend(fr_responses)

        # 按 raw_content hash 去重（同一产品可能在英法文中重复出现）
        seen: dict[str, SourceResponse] = {}
        for resp in responses:
            key = self._dedup_key(resp)
            if key not in seen:
                seen[key] = resp

        return list(seen.values())

    def _fetch_lang(
        self, lang: str, since: datetime | None = None
    ) -> list[SourceResponse]:
        """抓取指定语言的召回数据。"""
        base_url = self.BASE_URL_EN if lang == "en" else self.BASE_URL_FR
        responses: list[SourceResponse] = []
        page = 1
        max_pages = 10
        cutoff = since.isoformat() if since else None

        while page <= max_pages:
            url = f"{base_url}page={page}&limit=50"
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
                        language=lang,
                    )
                )
                break

            data = self._parse_json_response(resp.content, lang)
            if not data:
                break

            for item in data:
                source_resp = self._item_to_response(item, lang)
                # 时间过滤（cutoff_dt 是 datetime，published_at 是 string，string 比较安全）
                if cutoff and source_resp.published_at:
                    cutoff_iso = cutoff.isoformat()
                    if source_resp.published_at < cutoff_iso:
                        continue
                responses.append(source_resp)

            # 没有更多数据
            if len(data) < 50:
                break

            page += 1
            time.sleep(1)  # 礼貌限速

        return responses

    def _parse_json_response(self, content: bytes, lang: str) -> list[dict[str, Any]]:
        """解析 JSON 响应。Health Canada API 返回 JSON 列表或包装结构。"""
        import json

        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # 可能是 { "results": [...] } 或 { "data": [...] } 结构
                for key in ("results", "data", "recalls", "items"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                return [data]
            return []
        except json.JSONDecodeError:
            return []

    def _item_to_response(self, item: dict[str, Any], lang: str) -> SourceResponse:
        """将单个 API item 转换为 SourceResponse。"""
        # 尝试提取关键字段
        title = self._extract_field(item, ["title", "name", "product_name", "recalling_firm"])
        raw_content = self._extract_field(item, ["raw_content", "description", "hazard_summary", "product"])
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
        date_fields = ["date_published", "published_date", "recall_date", "date", "created_at"]
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
        # 中文格式
        m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        # 数字格式
        m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", value)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return None

    def _extract_severity(self, item: dict[str, Any], lang: str) -> str:
        """提取严重度等级。"""
        sev = item.get("severity", "") or item.get("risk_level", "") or item.get("type", "")
        sev.lower()
        severity_map = self.SEVERITY_MAP_FR if lang == "fr" else self.SEVERITY_MAP_EN
        return severity_map.get(sev, sev or "一般")

    def _extract_hazard(
        self, item: dict[str, Any], raw_content: bytes, lang: str
    ) -> str:
        """从 item 或 raw_content 中推断危害类型。"""
        hazard = item.get("hazard_type", "") or item.get("hazard", "") or item.get("risk", "")
        if hazard:
            return hazard.strip()

        # 从 raw_content 中检测关键词
        text = raw_content.decode("utf-8", errors="ignore").lower()
        for kw in self.HAZARD_KEYWORDS:
            if kw in text:
                return kw.capitalize()
        return "组合危险"

    def _extract_country(self, item: dict[str, Any]) -> str:
        """提取原产国。Health Canada 数据中原产国通常是 CA（加拿大）或进口国。"""
        country = item.get("country", "") or item.get("origin_country", "")
        if country:
            return country[:2].upper()
        return "CA"

    def _extract_manufacturer(self, item: dict[str, Any]) -> str:
        """提取制造商/召回方。"""
        return (
            item.get("manufacturer", "")
            or item.get("recalling_firm", "")
            or item.get("company", "")
            or item.get("firm", "")
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
            url = "https://healthcanada.gc.ca" + url
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
            "country": raw.country or "CA",
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
            "电子产品": ["electronic", "battery", "charger", "lamp", "led", "wire", "cable"],
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
