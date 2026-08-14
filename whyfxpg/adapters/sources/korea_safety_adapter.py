"""
KoreaSafetyAdapter — 韩国产品安全院（Korea Product Safety Korea / 제품안전정보원）数据源适配器。

支持韩文/英文双语数据。
数据来源：韩国产品安全院官网安全预警页面。

参考：https://www.kca.go.kr（韩国消费者院）/ 国立产品规格院安全数据。
"""

import re
from datetime import datetime, timezone
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class KoreaSafetyAdapter(BaseSourceAdapter):
    """
    韩国产品安全院（Korea Product Safety Korea）消费品安全预警数据适配器。

    支持：
    - 韩文安全预警数据
    - 英文摘要数据
    - 按时间范围过滤（since 参数）
    """

    source_id = "KOREA_SAFETY"
    source_name = "Korea Product Safety Korea (제품안전정보원)"

    # 韩国产品安全院/消费者院安全预警 API / 页面
    BASE_URL_KO: ClassVar[str] = "https://www.kca.go.kr"
    SAFETY_PATH: ClassVar[str] = "/pub/rec/civilappealL.do"
    BASE_URL: ClassVar[str] = BASE_URL_KO + SAFETY_PATH

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html, application/xhtml+xml, */*",
        "Accept-Language": "ko-KR, ko, en-US, en, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 危害类型关键词（韩文 + 英文）
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "화재", " brûlement", "fire", " burn",
        "감전", "shock", "electrical",
        " 질식", "choking", " suffocation",
        "중독", "toxic", "poison",
        "부상", "injury", "laceration", "fracture",
        "화학", "chemical",
        "미생물", "microbiological",
        "오염", "contamination",
        "결함", "defect",
        "붕괴", "collapse", "tip-over",
    ]

    # 严重度映射
    SEVERITY_MAP: ClassVar[dict[str, str]] = {
        "위험": "严重",
        "주의": "一般",
        "정보": "轻微",
        "dangerous": "严重",
        "caution": "一般",
        "information": "轻微",
    }

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "韩国产品安全院（Korea Product Safety Korea）"

    def _health_url(self) -> str:
        return self.BASE_URL_KO

    def health_check(self) -> bool:
        """检查韩国产品安全院网站是否可达。"""
        try:
            resp = self._session.get(self.BASE_URL_KO, timeout=self.TIMEOUT)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从韩国产品安全院安全预警页面抓取数据。
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
                    language="ko",
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
                    country="KR",
                    language=item.get("language", "ko"),
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
            text = html.decode("euc-kr", errors="ignore")

        items: list[dict[str, Any]] = []

        # 尝试多种 HTML 结构
        # 结构1: <table> <tr> 列表
        row_pattern = re.compile(
            r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>",
            re.DOTALL | re.IGNORECASE,
        )

        # 结构2: 公告列表 <li> 或 <article>
        list_pattern = re.compile(
            r"<li[^>]*class=\"[^\"]*(?:notice|alert|safety|recall|pub)[^\"]*\"[^>]*>(.*?)</li>",
            re.DOTALL | re.IGNORECASE,
        )

        article_pattern = re.compile(
            r"<article[^>]*>(.*?)</article>", re.DOTALL | re.IGNORECASE
        )

        found_count = 0
        for pattern in [row_pattern, list_pattern, article_pattern]:
            for match in pattern.finditer(text):
                block = match.group(1) if pattern == row_pattern else match.group(0)
                item = self._extract_item(block)
                if item.get("title") and len(item.get("title", "")) > 3:
                    items.append(item)
                    found_count += 1
            if found_count > 0:
                break

        # 如果正则无结果，尝试标题+日期组合模式
        if not items:
            title_date = re.compile(
                r"<h[23][^>]*>\s*([^<가-힣A-Za-z0-9\\s]+)\s*</h[23][^>]*>.*?"
                r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
                re.DOTALL | re.IGNORECASE,
            )
            for match in title_date.finditer(text[:80000]):
                title = match.group(1).strip()
                date_str = match.group(2).strip()
                if len(title) > 5:
                    items.append({
                        "title": html_module.unescape(title),
                        "published_at": self._normalize_date(date_str),
                        "raw_content": match.group(0).encode("utf-8") if isinstance(text, str) else block,
                        "language": "ko",
                    })

        return items

    def _extract_item(self, block: str) -> dict[str, Any]:
        """从 HTML 块中提取单个预警条目。"""
        import html as html_module

        # 提取标题
        title_match = re.search(
            r"<h[23][^>]*>\s*([^<]+)\s*</h[23]>", block, re.IGNORECASE
        )
        title = title_match.group(1).strip() if title_match else ""

        # 提取日期
        date_match = re.search(
            r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", block
        )
        date_str = date_match.group(1) if date_match else ""

        # 提取 URL
        url_match = re.search(
            r"href=[\"']([^\"']+)[\"']", block, re.IGNORECASE
        )
        url = url_match.group(1) if url_match else ""
        if url and not url.startswith("http"):
            url = self.BASE_URL_KO + url

        # 提取产品名
        product_match = re.search(
            r"(?:제품|product|item)[^가-힣]*[:\s]*([가-힣A-Za-z0-9\\s\-]+?)(?:,|\\n|<|$)",
            block, re.IGNORECASE
        )
        product_name = product_match.group(1).strip() if product_match else ""

        # 提取制造商/召回方
        firm_match = re.search(
            r"(?:제조|업체|firm|company|manufacturer)[^가-힣]*[:\s]*([가-힣A-Za-z0-9\\s\-]+?)(?:,|\\n|<|$)",
            block, re.IGNORECASE
        )
        manufacturer = firm_match.group(1).strip() if firm_match else ""

        # 推断危害类型
        hazard_type = self._infer_hazard(block)

        # 推断严重度
        severity = "一般"
        block_lower = block.lower()
        if any(kw in block_lower for kw in ["위험", "dangerous", "심각", "critical"]):
            severity = "严重"
        elif any(kw in block_lower for kw in ["정보", "information", "주의", "caution"]):
            severity = "一般"
        elif any(kw in block_lower for kw in ["轻微", "minor", "moderate"]):
            severity = "轻微"

        # 判断语言
        has_korean = bool(re.search(r"[가-힣]", title))
        language = "ko" if has_korean else "en"

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
        """从文本中推断危害类型（韩文+英文）。"""
        text_lower = text.lower()
        hazard_map = {
            "화재": "火灾", "fire": "fire",
            "감전": "触电", "electrical": "electrical",
            "중독": "中毒", "toxic": "toxic",
            "부상": "伤害", "injury": "injury",
            "화학": "化学危险", "chemical": "chemical",
            "미생물": "微生物危险", "microbiological": "microbiological",
            "오염": "污染", "contamination": "contamination",
            "결함": "产品缺陷", "defect": "defect",
            "붕괴": "坍塌", "collapse": "collapse",
            "질식": "窒息", "choking": "choking",
        }
        for kw, label in hazard_map.items():
            if kw in text_lower:
                return label
        return "组合危险"

    def _normalize_date(self, value: str) -> str:
        """将各种日期格式归一化为 YYYY-MM-DD。"""
        if not value:
            return ""
        # 数字格式
        m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", value)
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
            "country": raw.country or "KR",
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
            "电子产品": ["전자", "electronic", "battery", "charger", "lamp", "cable"],
            "儿童用品": ["아기", "유아", "child", "infant", "baby", "toy", "crib"],
            "食品": ["식품", "food", "meat", "dairy", "contaminant", "식품"],
            "化妆品": ["화장품", "cosmetic", "beauty"],
            "药品": ["의약품", "drug", "pharmaceutical", "medicine"],
            "医疗器械": ["의료기기", "medical", "device", "hospital"],
            "家用电器": ["가전", "appliance", "kitchen", "heater", "fan", "motor"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
