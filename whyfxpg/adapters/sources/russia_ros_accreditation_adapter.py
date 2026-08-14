"""
RussiaRosAccreditationAdapter - 俄罗斯联邦认证局 RosAccreditation
"""
from __future__ import annotations

import re
import typing
from datetime import datetime, timezone
from typing import Any

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class RussiaRosAccreditationAdapter(BaseSourceAdapter):
    source_id: str = "russia_ros_accreditation"
    source_name: str = "RosAccreditation (Федеральная служба по аккредитации)"
    BASE_URL: typing.ClassVar[str] = "https://fsa.gov.ru"
    TIMEOUT: typing.ClassVar[int] = 30
    SOURCES: typing.ClassVar[list[str]] = [
        "https://fsa.gov.ru/press/announces/",
        "https://fsa.gov.ru/activities/falsification/",
    ]
    SEVERITY_MAP: typing.ClassVar[dict[str, str]] = {
        "критический": "严重", "высокий": "高", "средний": "中",
        "низкий": "低", "незначительный": "轻微",
        "critical": "严重", "high": "高", "medium": "中", "low": "低", "minor": "轻微",
    }
    HAZARD_KEYWORDS: typing.ClassVar[list[tuple[str, str]]] = [
        ("пожар", "火灾"), ("взрыв", "爆炸"), ("отравление", "中毒"),
        ("травма", "伤害"), ("удушение", "窒息"), ("химический", "化学危害"),
        ("некачественный", "质量缺陷"), ("брак", "缺陷产品"), ("опасная продукция", "危险产品"),
    ]

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "WHYFXPG/1.0", "Accept-Language": "ru-RU, ru, en-US, en"})

    @property
    def source_name_zh(self) -> str:
        return "俄罗斯联邦认证局"

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        responses: list[SourceResponse] = []
        for url in self.SOURCES:
            try:
                resp = self._session.get(url, timeout=self.TIMEOUT)
                if resp.status_code >= 400:
                    continue
                items = self._parse_page(resp.content, url)
                if since:
                    items = [r for r in items if r.published_at is None or r.published_at >= since]
                responses.extend(items)
            except Exception:  # noqa: BLE001, S112
                continue
        return responses

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        text = raw.decode("utf-8", errors="replace")
        return self._extract_items(text)

    def health_check(self) -> bool:
        try:
            r = self._session.get(self.BASE_URL, timeout=10)
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def _parse_page(self, raw: bytes, url: str) -> list[SourceResponse]:
        text = raw.decode("utf-8", errors="replace")
        items = self._extract_items(text)
        responses: list[SourceResponse] = []
        for item in items:
            try:
                dt = datetime.strptime(item["published_date"], "%d.%m.%Y").replace(tzinfo=timezone.utc) if item.get("published_date") else datetime.now(timezone.utc)
            except Exception:  # noqa: BLE001
                dt = datetime.now(timezone.utc)
            raw_text = item.get("raw_text", "")
            raw_content: bytes | str = raw_text.encode("utf-8") if isinstance(raw_text, str) else raw_text
            responses.append(SourceResponse(
                source_id=self.source_id,
                url=item.get("source_url", url),
                title=item.get("title", ""),
                hazard_type=item.get("hazard_type", "其他"),
                severity=item.get("severity", "一般"),
                published_at=dt.isoformat(),
                raw_content=raw_content,
                country="RU",
                language="ru"))
        return responses

    def _extract_items(self, text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        items.extend(self._extract_json_ld(text))
        if not items:
            items.extend(self._extract_rss(text))
        if not items:
            items.extend(self._extract_html_items(text))
        return items

    def _extract_json_ld(self, text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.DOTALL | re.IGNORECASE):
            import json
            try:
                data = json.loads(m.group(1))
                for entry in (data if isinstance(data, list) else [data]):
                    if entry.get("@type") in ("Article", "NewsArticle"):
                        body = entry.get("articleBody", "")
                        items.append({
                            "title": entry.get("headline", ""), "description": entry.get("description", ""),
                            "published_date": self._date_field(entry), "source_url": entry.get("url", ""),
                            "raw_text": body, "hazard_type": self._infer_hazard(body), "severity": self._infer_severity(body)})
            except Exception:  # noqa: BLE001, S112
                continue
        return items

    def _extract_rss(self, text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for m in re.finditer(r'<item>(.*?)</item>', text, re.DOTALL | re.IGNORECASE):
            it = m.group(1)
            title = self._tag(it, "title"); link = self._tag(it, "link")
            date_str = self._tag(it, "pubDate"); desc = self._tag(it, "description")
            if title:
                items.append({
                    "title": title.strip(), "event_id": link or "", "published_date": self._parse_rss_date(date_str or ""),
                    "source_url": (link or "").strip(), "raw_text": desc or "", "description": (desc or "").strip(),
                    "hazard_type": self._infer_hazard(desc or ""), "severity": self._infer_severity(desc or "")})
        return items

    def _extract_html_items(self, text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for m in re.finditer(r'(\d{1,2}[./\-]\d{2}[./\-]\d{4})\s*[–-]?\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', text, re.IGNORECASE):
            d, link, title = m.groups()
            items.append({
                "title": title.strip(), "event_id": link or "", "published_date": self._norm_date(d),
                "source_url": (link or "").strip(), "raw_text": "", "description": "",
                "hazard_type": "其他", "severity": "一般"})
        return items

    def _tag(self, xml: str, tag: str) -> str | None:
        m = re.search(rf'<{tag}>(.*?)</{tag}>', xml, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _date_field(self, d: dict) -> str:
        for f in ("datePublished", "dateCreated", "publishDate"):
            v = d.get(f)
            if v:
                return str(v)
        return ""

    def _parse_rss_date(self, s: str) -> str:
        import email.utils
        try:
            return email.utils.parsedate_to_datetime(s).strftime("%d.%m.%Y")
        except Exception:  # noqa: BLE001, S110
            pass
        for fmt in ("%d %b %Y", "%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(s.strip(), fmt).replace(tzinfo=timezone.utc).strftime("%d.%m.%Y")
            except Exception:  # noqa: BLE001, S112
                continue
        return s

    def _norm_date(self, s: str) -> str:
        p = re.split(r'[./\-]', s.strip())
        if len(p) == 3 and len(p[2]) == 4:
            return f"{p[0].zfill(2)}.{p[1].zfill(2)}.{p[2]}"
        if len(p) == 3 and len(p[0]) == 4:
            return f"{p[2].zfill(2)}.{p[1].zfill(2)}.{p[0]}"
        return s

    def _infer_severity(self, text: str) -> str:
        t = text.lower()
        for kw, sev in self.SEVERITY_MAP.items():
            if kw.lower() in t:
                return sev
        return "一般"

    def _infer_hazard(self, text: str) -> str:
        t = text.lower()
        for kw, h in self.HAZARD_KEYWORDS:
            if kw.lower() in t:
                return h
        return "其他"
