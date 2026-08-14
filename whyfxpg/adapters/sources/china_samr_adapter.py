"""
ChinaSAMRAdapter — 中国国家市场监督管理总局（SAMR）数据源适配器。

数据来源：国家市场监督管理总局缺陷产品召回信息 / samr.gov.cn

参考：https://www.samr.gov.cn/zwgk/ztzl/yaopin召回/
"""

import hashlib
import re
import time
from datetime import datetime
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class ChinaSAMRAdapter(BaseSourceAdapter):
    """
    中国国家市场监督管理总局缺陷产品召回数据适配器。

    支持：
    - 中文召回数据（主要）
    - 英文召回数据（如有）
    - 按时间范围过滤（since 参数）
    """

    source_id = "CHINA_SAMR"
    source_name = "China SAMR - State Administration for Market Regulation"

    # SAMR 缺陷产品召回信息公示系统
    BASE_URL: ClassVar[str] = "https://www.samr.gov.cn/zwgk/ztzl/yaopin召回/"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html, application/xhtml+xml, application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN, zh;q=0.9, en;q=0.8",
    }

    TIMEOUT: ClassVar[int] = 30

    # 严重度映射
    SEVERITY_MAP: ClassVar[dict[str, str]] = {
        "严重": "严重",
        "重大": "严重",
        "一般": "一般",
        "较轻": "轻微",
        "轻微": "轻微",
    }

    # 危害类型常用关键词
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "火灾", "爆炸", "燃烧", "电击", "触电", "窒息", "噎塞",
        "中毒", "有毒", "划伤", "割伤", "骨折", "卡住",
        "溺水", "化学", "微生物", "污染", "缺陷", "故障",
        "漏电", "过热", "起火", "爆裂", "破损", "裂纹",
    ]

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "国家市场监督管理总局缺陷产品召回"

    def _health_url(self) -> str:
        return self.BASE_URL

    def health_check(self) -> bool:
        """检查 SAMR 网站是否可达。"""
        try:
            resp = self._session.get(self.BASE_URL, timeout=self.TIMEOUT)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底，刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 SAMR 缺陷产品召回信息系统抓取数据。

        官方公开页面为 HTML 列表页，需要解析分页结构。
        """
        responses: list[SourceResponse] = []
        cutoff = since.isoformat() if since else None

        page = 1
        max_pages = 10
        seen: dict[str, SourceResponse] = {}

        while page <= max_pages:
            url = f"{self.BASE_URL}index_{page}.html"
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
                        language="zh",
                    )
                )
                break

            items = self._parse_html_list(resp.content)
            if not items:
                break

            for item in items:
                source_resp = self._item_to_response(item)
                # 时间过滤
                if cutoff and source_resp.published_at and source_resp.published_at < cutoff:
                    continue
                key = self._dedup_key(source_resp)
                if key not in seen:
                    seen[key] = source_resp

            if len(items) < 20:  # 假设每页约 20 条
                break

            page += 1
            time.sleep(1)  # 礼貌限速

        return list(seen.values())

    def _parse_html_list(self, content: bytes) -> list[dict[str, Any]]:
        """解析 SAMR HTML 召回列表页。"""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return self._parse_html_list_fallback(content)

        try:
            soup = BeautifulSoup(content, "html.parser")
            items: list[dict[str, Any]] = []

            # 常见列表结构：<ul class="xx"> <li> <a href="...">标题</a> <span>日期</span> </li> </ul>
            for li in soup.find_all("li"):
                a_tag = li.find("a")
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                if not title:
                    continue

                # 日期可能在 <span> 或 <font> 等标签中
                date_str = ""
                for sibling in li.find_all(["span", "font", "em", "b"]):
                    text = sibling.get_text(strip=True)
                    if re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", text):
                        date_str = text
                        break

                items.append({
                    "title": title,
                    "url": href if href.startswith("http") else f"https://www.samr.gov.cn{href}",
                    "date": date_str,
                })

            # 备选：<table> 结构
            if not items:
                for tr in soup.find_all("tr"):
                    cells = tr.find_all("td")
                    if len(cells) >= 2:
                        a_tag = cells[0].find("a")
                        if a_tag:
                            title = a_tag.get_text(strip=True)
                            href = a_tag.get("href", "")
                            date_str = cells[-1].get_text(strip=True)
                            if title:
                                items.append({
                                    "title": title,
                                    "url": href if href.startswith("http") else f"https://www.samr.gov.cn{href}",
                                    "date": date_str,
                                })

            return items
        except Exception:  # noqa: BLE001 — 解析容错
            return []

    def _parse_html_list_fallback(self, content: bytes) -> list[dict[str, Any]]:
        """无 BeautifulSoup 时的正则备用解析。"""
        items: list[dict[str, Any]] = []
        text = content.decode("utf-8", errors="ignore")

        # 匹配 <a href="...">标题</a> 相关结构
        pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>')
        for match in pattern.finditer(text):
            href = match.group(1)
            title = match.group(2).strip()
            if title and len(title) > 4:
                full_url = href if href.startswith("http") else f"https://www.samr.gov.cn{href}"
                items.append({"title": title, "url": full_url, "date": ""})

        return items[:50]  # 限制数量

    def _item_to_response(self, item: dict[str, Any]) -> SourceResponse:
        """将解析出的 item 字典转换为 SourceResponse。"""
        title = item.get("title", "")
        url = item.get("url", "")
        date_str = item.get("date", "")

        published_at = self._normalize_date(date_str) if date_str else None

        # 从标题推断危害类型
        hazard_type = self._infer_hazard(title)

        return SourceResponse(
            source_id=self.source_id,
            url=url,
            raw_content=title.encode("utf-8") if isinstance(title, str) else title,
            title=title,
            published_at=published_at,
            country="CN",
            language="zh",
            hazard_type=hazard_type,
            severity="一般",
            product_name="",
            manufacturer="",
            raw_fields=dict(item),
            status="ok",
        )

    def _normalize_date(self, value: str) -> str | None:
        """将各种日期格式归一化为 YYYY-MM-DD。"""
        # 中文格式：2024年12月1日 / 2024-12-01 / 2024/12/01
        m = re.match(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return None

    def _infer_hazard(self, text: str) -> str:
        """从标题文本中推断危害类型。"""
        for kw in self.HAZARD_KEYWORDS:
            if kw in text:
                return kw
        return "缺陷"

    def _dedup_key(self, resp: SourceResponse) -> str:
        """生成去重键：基于标题的 hash。"""
        sig = f"{resp.title}".encode()
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
        elif not isinstance(text, str):
            text = str(text)

        return {
            "source_id": self.source_id,
            "source_url": raw.url,
            "title": raw.title or raw.url,
            "product_name": raw.product_name,
            "brand": "",
            "model": "",
            "hs_code": "",
            "product_category": self._infer_category(text),
            "country": raw.country or "CN",
            "manufacturer": raw.manufacturer,
            "hazard_type": raw.hazard_type or "缺陷",
            "hazard_desc": text[:500],
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
            "extraction_confidence": 0.5,
            "review_status": "auto",
            "extracted_language": raw.language,
        }

    def _infer_category(self, text: str) -> str:
        """根据文本内容推断产品类别。"""
        category_keywords = {
            "电子产品": ["电子", "电池", "充电器", "灯具", "电线", "电缆", "电器", "电机"],
            "儿童用品": ["儿童", "婴儿", "玩具", "童车", "床", "座椅", "用品"],
            "食品": ["食品", "肉类", "乳制品", "有机", "污染", "细菌", "微生物"],
            "化妆品": ["化妆品", "护肤", "美容", "美发"],
            "药品": ["药品", "药物", "医疗器械", "生物制品"],
            "医疗器械": ["医疗", "器械", "诊断", "植入"],
            "家用电器": ["家电", "厨房", "加热器", "风扇", "马达", "泵"],
            "汽车配件": ["汽车", "车辆", "轮胎", "刹车", "安全带", "气囊"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text for kw in keywords):
                return category
        return "普通机电"
