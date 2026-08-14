"""
MexicoPROFECOAdapter — 墨西哥 PROFECO（Procuraduría Federal del Consumidor）数据源适配器。

支持西班牙语（es）消费者预警数据。
数据来源：PROFECO 开放数据 / Alertasmaster 数据库。

参考：https://www.profeco.gob.mx
"""

import hashlib
import re
import time
from datetime import datetime
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class MexicoPROFECOAdapter(BaseSourceAdapter):
    """
    墨西哥 PROFECO 消费者预警数据适配器。

    支持：
    - 西班牙语预警数据（lang=es）
    - 按时间范围过滤（since 参数）
    """

    source_id = "MEXICO_PROFECO"
    source_name = "PROFECO - Procurador Federal del Consumidor"

    # PROFECO 开放数据 API endpoints
    BASE_URL_ES: ClassVar[str] = "https://www.profeco.gob.mx/alertasmaster/"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "es-MX, es-ES, es-419, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 严重度映射（西班牙语 → 统一标签）
    SEVERITY_MAP_ES: ClassVar[dict[str, str]] = {
        "grave": "严重",
        "serio": "严重",
        "moderado": "一般",
        "menor": "轻微",
        "leve": "轻微",
    }

    # 危害类型常用关键词（西班牙语）
    HAZARD_KEYWORDS: ClassVar[list[str]] = [
        "incendio", "flama", "quemadura", "eléctrico", "electrocución", "choque",
        "intoxicación", "tóxico", "envenenamiento", "corte", "fractura",
        "atrapamiento", "asfixia", "ahogamiento", "químico", "microbiológico",
        "contaminación", "defecto", "fallo", "riesgo", "peligro",
    ]

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "墨西哥消费者保护局预警数据库"

    def _health_url(self) -> str:
        return self.BASE_URL_ES

    def health_check(self) -> bool:
        """检查 PROFECO 网站是否可达。"""
        try:
            resp = self._session.get(
                self.BASE_URL_ES,
                timeout=self.TIMEOUT,
            )
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底，刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 PROFECO 消费者预警数据库抓取数据。
        """
        responses: list[SourceResponse] = []
        cutoff = since.isoformat() if since else None

        # 尝试抓取 PROFECO 预警数据
        page = 1
        max_pages = 10

        while page <= max_pages:
            url = f"{self.BASE_URL_ES}busca_avanzada.aspx?page={page}"
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
                        language="es",
                    )
                )
                break

            items = self._parse_html_response(resp.content, resp.apparent_encoding or "utf-8")
            if not items:
                break

            for item in items:
                source_resp = self._item_to_response(item)
                # 时间过滤
                if cutoff and source_resp.published_at and source_resp.published_at < cutoff:
                    continue
                responses.append(source_resp)

            # 没有更多数据
            if len(items) < 20:
                break

            page += 1
            time.sleep(1.5)  # 礼貌限速

        return responses

    def _parse_html_response(self, content: bytes, encoding: str = "utf-8") -> list[dict[str, Any]]:
        """解析 HTML 响应，提取预警条目。"""
        try:
            text = content.decode(encoding, errors="replace")
        except (UnicodeDecodeError, LookupError):
            text = content.decode("utf-8", errors="replace")

        items: list[dict[str, Any]] = []

        # PROFECO 页面通常有表格或列表结构
        # 尝试匹配常见的 HTML 结构模式
        product_patterns = [
            re.compile(r'<td[^>]*class="[^"]*producto[^"]*"[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE),
            re.compile(r'<td[^>]*>(.*?producto.*?)</td>', re.DOTALL | re.IGNORECASE),
        ]
        firm_patterns = [
            re.compile(r'<td[^>]*class="[^"]*empresa[^"]*"[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE),
            re.compile(r'<td[^>]*>(.*?empresa.*?|.*?fabricante.*?)</td>', re.DOTALL | re.IGNORECASE),
        ]
        date_patterns = [
            re.compile(r'<td[^>]*class="[^"]*fecha[^"]*"[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE),
        ]

        # 提取所有表格行
        row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
        rows = row_pattern.findall(text)

        for row in rows:
            item: dict[str, Any] = {}

            # 提取产品名称
            for pat in product_patterns:
                match = pat.search(row)
                if match:
                    item["producto"] = self._clean_html(match.group(1))
                    break

            # 提取企业/制造商
            for pat in firm_patterns:
                match = pat.search(row)
                if match:
                    item["empresa"] = self._clean_html(match.group(1))
                    break

            # 提取日期
            for pat in date_patterns:
                match = pat.search(row)
                if match:
                    item["fecha"] = self._clean_html(match.group(1))
                    break

            # 提取危险描述
            hazard_match = re.search(
                r'<td[^>]*>(.*?peligro.*?|.*?riesgo.*?|.*?descripción.*?)</td>',
                row,
                re.DOTALL | re.IGNORECASE
            )
            if hazard_match:
                item["descripcion"] = self._clean_html(hazard_match.group(1))

            if item:
                items.append(item)

        return items

    def _clean_html(self, html: str) -> str:
        """去除 HTML 标签，清理文本。"""
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _item_to_response(self, item: dict[str, Any]) -> SourceResponse:
        """将单个条目转换为 SourceResponse。"""
        producto = item.get("producto", "")
        empresa = item.get("empresa", "")
        descripcion = item.get("descripcion", "")
        fecha = item.get("fecha", "")

        raw_content = f"{producto} {empresa} {descripcion}".strip()
        if isinstance(raw_content, str):
            raw_content_bytes = raw_content.encode("utf-8")
        else:
            raw_content_bytes = raw_content

        published_at = self._normalize_date(fecha) if fecha else None
        severity = self._extract_severity(descripcion)
        hazard_type = self._extract_hazard(descripcion, raw_content_bytes)
        manufacturer = self._clean_manufacturer_name(empresa)

        return SourceResponse(
            source_id=self.source_id,
            url=self.BASE_URL_ES,
            raw_content=raw_content_bytes,
            title=producto or descripcion[:100],
            published_at=published_at,
            country="MX",
            language="es",
            hazard_type=hazard_type,
            severity=severity,
            product_name=producto,
            manufacturer=manufacturer,
            raw_fields=dict(item),
            status="ok",
        )

    def _normalize_date(self, value: str) -> str | None:
        """将各种日期格式归一化为 YYYY-MM-DD。"""
        if not value:
            return None

        value = value.strip()

        # 西班牙语格式：dd/mm/yyyy 或 dd-mm-yyyy
        m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", value)
        if m:
            day, month, year = m.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"

        # ISO 格式
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        return None

    def _extract_severity(self, text: str) -> str:
        """从西班牙语文本中提取严重度等级。"""
        text_lower = text.lower()
        for key, label in self.SEVERITY_MAP_ES.items():
            if key in text_lower:
                return label
        return "一般"

    def _extract_hazard(self, text: str, raw_content: bytes) -> str:
        """从文本中推断危害类型。"""
        text_lower = text.lower()
        if not text_lower:
            text_lower = raw_content.decode("utf-8", errors="ignore").lower()

        for kw in self.HAZARD_KEYWORDS:
            if kw in text_lower:
                return kw.capitalize()
        return "组合危险"

    def _clean_manufacturer_name(self, name: str) -> str:
        """清理制造商名称。"""
        if not name:
            return ""
        # 去除多余空白和常见前缀
        name = re.sub(r'\s+', ' ', name).strip()
        name = re.sub(r'^(empresa:|fabricante:|marca:)\s*', '', name, flags=re.IGNORECASE)
        return name

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
            "country": raw.country or "MX",
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
        """根据西班牙语文本内容推断产品类别。"""
        text_lower = text.lower()
        category_keywords = {
            "电子产品": ["electrónico", "batería", "cargador", "lámpara", "led", "cable", "alambre"],
            "儿童用品": ["niño", "infante", "bebé", "juguete", "cuna", "coche", "silla"],
            "食品": ["alimento", "carne", "lácteo", "orgánico", "contaminante", "bacterial"],
            "化妆品": ["cosmético", "piel", "crema", "loción", "belleza"],
            "药品": ["droga", "farmacéutico", "medicamento", "tableta", "cápsula"],
            "医疗器械": ["médico", "dispositivo", "implante", "diagnóstico", "hospital"],
            "家用电器": ["electrodoméstico", "cocina", "calefactor", "ventilador", "motor", "bomba"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
