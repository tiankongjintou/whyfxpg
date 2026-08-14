"""
JapanCAAAdapter — 日本消費者庁 (Consumer Affairs Agency) 数据源适配器。

日本消费者厅发布产品安全召回信息（事故・被害情報 & 回収情報）。
数据格式：HTML 列表页面，支持 Shift-JIS / UTF-8 双重编码自动识别。

参考：https://www.caa.go.jp/
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_port import FetchedPage

try:
    from charset_normalizer import detect as _charset_detect
except ImportError:  # pragma: no cover — requests 依赖 charset_normalizer
    _charset_detect = None

logger = logging.getLogger(__name__)

# 日本消费者厅召回信息页面（示例 URL，实际抓取时以配置为准）
DEFAULT_BASE_URL = "https://www.caa.go.jp"
DEFAULT_RECALL_PATH = "/recall/list/"


class JapanCAAAdapter:
    """
    日本消费者厅（Consumer Affairs Agency）数据源适配器。

    特点：
    - 自动检测页面编码（Shift-JIS / UTF-8 / EUC-JP）
    - 解析 HTML 召回列表，提取产品名称、制造商、危害类型、发布日期
    - 提供健康检查接口

    使用方式::

        adapter = JapanCAAAdapter()
        pages = adapter.fetch(since=datetime(2026, 1, 1))
        for page in pages:
            event = adapter.parse(page)
            print(event)
    """

    source_id = "japan_caa"
    source_name = "日本消費者庁（消費者庁）"

    # 日本消费者厅编码常见为 Shift-JIS，次为 UTF-8
    _ENCODINGS_TO_TRY: ClassVar[list[str]] = [
        "shift_jis",
        "utf-8",
        "euc-jp",
        "iso-2022-jp",
    ]

    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str = DEFAULT_BASE_URL,
        recall_path: str = DEFAULT_RECALL_PATH,
        timeout: int = 30,
    ):
        self.session = session or requests.Session()
        self.base_url = base_url
        self.recall_path = recall_path
        self.timeout = timeout

    # ─── 编码检测 ────────────────────────────────────────────────

    def _detect_encoding(self, raw_bytes: bytes) -> str:
        """
        使用 charset_normalizer 检测字节流的字符编码。

        检测顺序优先 Shift-JIS（消费者厅最常用），其次 UTF-8。
        检测结果置信度低于 0.6 时降级到 Shift-JIS（消费者厅历史数据多为此编码）。
        """
        detected = None
        confidence = 0.0

        if _charset_detect is not None:
            result = _charset_detect(raw_bytes)
            detected = (result.get("encoding") or "").lower().strip()
            confidence = result.get("confidence", 0) or 0.0

        if not detected:
            logger.warning("charset_normalizer 未检测到编码，默认使用 Shift-JIS")
            return "shift_jis"

        # 标准化编码名称
        if detected in ("shift-jis", "shift_ms", "windows-31j"):
            return "shift_jis"
        if detected in ("utf-8", "utf8"):
            return "utf-8"
        if detected in ("euc-jp", "eucjp"):
            return "euc-jp"
        if detected in ("iso-2022-jp", "iso2022jp"):
            return "iso-2022-jp"

        # 置信度低时强制使用 Shift-JIS（消费者厅历史页面大量为 Shift-JIS）
        if confidence < 0.6:
            logger.warning(
                "编码检测置信度 %.2f < 0.6，强制使用 Shift-JIS（消费者厅历史数据默认编码）",
                confidence,
            )
            return "shift_jis"

        return detected

    def _decode_content(self, raw_bytes: bytes) -> str:
        """智能解码：先尝试 chardet 检测，失败则遍历候选编码列表。"""
        encoding = self._detect_encoding(raw_bytes)
        try:
            return raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            logger.warning("使用 %s 解码失败，遍历候选编码列表", encoding)

        for enc in self._ENCODINGS_TO_TRY:
            try:
                return raw_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue

        # 最终兜底：忽略错误解码（保留可读 ASCII/半角内容）
        return raw_bytes.decode("utf-8", errors="ignore")

    # ─── fetch ───────────────────────────────────────────────────

    def fetch(self, since: datetime | None = None) -> list[FetchedPage]:
        """
        从日本消费者厅抓取召回信息列表页。

        Args:
            since: 仅返回此日期之后的召回记录（默认返回最近 30 天）。

        Returns:
            FetchedPage 列表，每条记录对应一个召回事项。
        """
        if since is None:
            since = datetime.now() - timedelta(days=30)  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

        url = f"{self.base_url}{self.recall_path}"
        pages: list[FetchedPage] = []

        try:
            started = time.perf_counter()
            resp = self.session.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "ja,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            latency_ms = int((time.perf_counter() - started) * 1000)

        except requests.RequestException as e:
            logger.error("日本消費者庁への接続に失敗しました: %s", e)
            return [
                FetchedPage(
                    source_id=self.source_id,
                    url=url,
                    content=b"",
                    content_type="unknown",
                    content_hash="",
                    status="error",
                    error_msg=str(e),
                )
            ]

        raw_bytes = resp.content
        content_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 解码（处理日文编码）
        content_str = self._decode_content(raw_bytes)
        # 重新编码为 UTF-8 字节存入 content（统一格式）
        content = content_str.encode("utf-8")

        pages.append(
            FetchedPage(
                source_id=self.source_id,
                url=resp.url,
                content=content,
                content_type=resp.headers.get("Content-Type", "text/html"),
                content_hash=content_hash,
                fetched_at=datetime.now().isoformat(),  # noqa: DTZ005
                latency_ms=latency_ms,
                content_length=len(content),
                status="ok",
            )
        )

        return pages

    # ─── parse ───────────────────────────────────────────────────

    def parse(self, raw: FetchedPage) -> dict[str, Any]:
        """
        将日本消费者厅的原始 HTML 页面解析为风险事件字典。

        解析字段（映射到 risk_events 表结构）：
          - event_id         (UUID)
          - source_id        = "japan_caa"
          - source_url       = raw.url
          - publish_date     (从页面提取的发布日期)
          - title            (召回产品名称)
          - product_name     (产品名称)
          - manufacturer     (制造商/品牌)
          - hazard_type      (危害类型)
          - hazard_desc      (危害描述)
          - severity_level   (严重程度)
          - country          = "JP"

        Args:
            raw: fetch() 返回的 FetchedPage 对象。

        Returns:
            标准风险事件字典。
        """
        import uuid

        text = raw.content.decode("utf-8", errors="ignore")

        # 日本消费者厅页面通常包含以下信息区块
        # <li class="recall-item">...<span class="product">产品名</span>...<span class="date">2026-01-15</span>...</li>
        # 实际 CSS 类名需按实际页面调整，此处使用正则兜底提取

        # 提取发布日期（优先从页面元数据提取）
        publish_date = self._extract_date(text)

        # 提取产品名称（正则兜底）
        product_name = self._extract_field(text, r"(?:製品名|商品名|対象製品)[:：]?\s*([^\s　]{2,50})")
        if not product_name:
            product_name = self._extract_field(text, r"<title>([^<]{2,100})</title>") or "日本消費者庁公表情報"

        # 提取制造商
        manufacturer = self._extract_field(
            text, r"(?:制造商|製造者|ブランド|企業名)[:：]?\s*([^\s　<]{2,50})"
        ) or ""

        # 提取危害类型（燃烧、触电、伤害等）
        hazard_type = self._extract_hazard_type(text)

        # 提取严重程度
        severity_level = self._extract_severity(text)

        event = {
            "event_id": str(uuid.uuid4()),
            "source_id": self.source_id,
            "source_url": raw.url,
            "publish_date": publish_date or datetime.now().strftime("%Y-%m-%d"),  # noqa: DTZ005
            "title": f"【日本消費者庁】{product_name}",
            "product_name": product_name,
            "brand": "",
            "model": "",
            "hs_code": "",
            "product_category": self._classify_product_category(text),
            "country": "JP",
            "manufacturer": manufacturer,
            "hazard_type": hazard_type,
            "hazard_desc": self._extract_description(text),
            "severity_level": severity_level,
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
            "original_text": text[:2000],  # 限制原始文本长度
            "extracted_at": datetime.now().isoformat(),  # noqa: DTZ005
            "evaluated_at": None,
            "config_version": "",
            "model_version": "",
            "extraction_confidence": 0.5,
            "review_status": "auto",
        }

        return event

    def _extract_field(self, text: str, pattern: str) -> str:
        """从文本中用正则提取第一个匹配组。"""
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_date(self, text: str) -> str | None:
        """提取发布日期，尝试多种日期格式。"""
        # 格式：2026年1月15日、2026-01-15、2026/01/15
        patterns = [
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            r"(\d{4})[-/](\d{2})[-/](\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if "年" in pattern:
                    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
                return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return None

    def _extract_hazard_type(self, text: str) -> str:
        """根据关键词推断危害类型。"""
        text_lower = text.lower()
        hazard_keywords = {
            "燃烧": ["燃え", "火災", "火事", "着火", "発火"],
            "触电": ["感電", "電気", "ショート"],
            "伤害": ["怪我", "負傷", "手指", "切創", "裂傷"],
            "窒息": ["窒息", "誤飲", "誤嚥"],
            "中毒": ["中毒", "有害", "化学"],
            "倒塌": ["倒塌", "落下", "転落"],
        }
        for hazard, keywords in hazard_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return hazard
        return "组合危险"

    def _extract_severity(self, text: str) -> str:
        """从文本关键词推断严重程度。"""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["重傷", "死亡", "大火", "重大"]):
            return "严重"
        if any(kw in text_lower for kw in ["軽傷", "小火", "注意", "自主"]):
            return "轻微"
        return "一般"

    def _extract_description(self, text: str) -> str:
        """提取危害描述段落。"""
        # 尝试提取 <p> 标签中的描述内容
        desc = self._extract_field(text, r"<p[^>]*>([^<]{20,500})</p>")
        if desc:
            return desc[:500]
        # 退而求其次：提取含有危害关键词的句子
        sentences = re.split(r"[。．\n]", text)
        for sent in sentences:
            if any(kw in sent for kw in ["燃え", "火災", "怪我", "破裂", "故障", "落下"]):
                return sent.strip()[:500]
        return ""

    def _classify_product_category(self, text: str) -> str:
        """根据产品类别关键词分类。"""
        text_lower = text.lower()
        category_keywords = {
            "家用电器": ["電気", "家电", "電源", "コード", "充電", "バッテリー"],
            "儿童用品": ["子供", "乳幼児", "玩具", "ベビー", "チャイルド"],
            "厨房用品": ["キッチン", "調理", "食器", "コンロ", "ガス"],
            "家具": ["家具", "収納", "棚", "椅子", "ソファ"],
            "个人护理": ["美容", "健康", "マッサージ", "ヘアケア"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"

    # ─── health_check ────────────────────────────────────────────

    def health_check(self) -> bool:
        """
        健康检查：验证日本消费者厅网站是否可达。

        Returns:
            True — 网站正常返回；False — 连接失败或超时。
        """
        try:
            resp = self.session.head(
                f"{self.base_url}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
                allow_redirects=True,
            )
            return resp.status_code < 500
        except requests.RequestException:
            return False

    # ─── 注册支持 ─────────────────────────────────────────────────

    @property
    def source_id_prop(self) -> str:
        return self.source_id

    @property
    def source_name_prop(self) -> str:
        return self.source_name
