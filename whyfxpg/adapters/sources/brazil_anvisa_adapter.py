"""
BrazilANVISAAdapter — 巴西 ANVISA（Agência Nacional de Vigilância Sanitária）数据源适配器。

数据来源：ANVISA 开放数据 / 召回公告系统（gov.br/anvisa）。
语言：葡萄牙语（pt）。

参考：https://www.gov.br/anvisa/
"""

import hashlib
import re
import time
from datetime import datetime
from typing import Any, ClassVar

import requests

from whyfxpg.ports.source_adapter import BaseSourceAdapter, SourceResponse


class BrazilANVISAAdapter(BaseSourceAdapter):
    """
    巴西 ANVISA 产品召回/预警数据适配器。

    ANVISA 是巴西国家卫生监督局，负责医疗器械、药品、食品等产品的上市后监管。
    数据通常以葡萄牙语发布。

    支持：
    - 葡萄牙语（pt）原始数据
    - 按时间范围过滤（since 参数）
    - gov.br 域名标准化处理
    """

    source_id = "BRAZIL_ANVISA"
    source_name = "ANVISA - Agência Nacional de Vigilância Sanitária"

    # ANVISA 开放数据 API endpoints（gov.br 域名）
    BASE_URL: ClassVar[str] = "https://www.gov.br/anvisa/pt-br"

    # 备用 API 端点（直接调用数据结构）
    API_URL: ClassVar[str] = "https://www.gov.br/anvisa/api"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html",
        "Accept-Language": "pt-BR, pt, */*",
    }

    TIMEOUT: ClassVar[int] = 30

    # 严重度映射（葡萄牙语 → 统一标签）
    SEVERITY_MAP_PT: ClassVar[dict[str, str]] = {
        "grave": "严重",
        "grave/defeito": "严重",
        "moderado": "一般",
        "moderada": "一般",
        "leve": "轻微",
        "leve/sem risco": "轻微",
    }

    # 危害类型常用关键词（葡萄牙语）
    HAZARD_KEYWORDS_PT: ClassVar[list[str]] = [
        "incêndio", "queimadura", "choque", "elétrico", "atropelamento",
        "tóxico", "envenenamento", "lacreração", "fratura", "aprisionamento",
        "sufocamento", "afogamento", "químico", "microbiológico",
        "contaminação", "defeito", "quebra", "falha",
    ]

    # 危害类型英译映射
    HAZARD_TRANSLATIONS: ClassVar[dict[str, str]] = {
        "incêndio": "fire",
        "queimadura": "burn",
        "choque elétrico": "electrical shock",
        "elétrico": "electrical",
        "tóxico": "toxic",
        "envenenamento": "poisoning",
        "lacreração": "laceration",
        "fratura": "fracture",
        "aprisionamento": "entrapment",
        "sufocamento": "suffocation",
        "afogamento": "drowning",
        "químico": "chemical",
        "microbiológico": "microbiological",
        "contaminação": "contamination",
        "defeito": "defect",
        "quebra": "breakdown",
        "falha": "failure",
    }

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(self.HEADERS)

    @property
    def source_name_zh(self) -> str:
        return "巴西 ANVISA 国家卫生监督局"

    def _health_url(self) -> str:
        return self.BASE_URL

    def health_check(self) -> bool:
        """检查 ANVISA (gov.br) 网站是否可达。"""
        try:
            resp = self._session.get(
                self.BASE_URL,
                timeout=self.TIMEOUT,
            )
            return resp.status_code < 500
        except Exception:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return False

    def fetch(self, since: datetime | None = None) -> list[SourceResponse]:
        """
        从 ANVISA 召回/预警数据系统抓取数据。

        ANVISA 主要通过 gov.br 域发布数据，支持 RSS/API/网页三种形式。
        这里优先尝试开放数据 API，失败则降级到网页抓取。
        """
        responses: list[SourceResponse] = []

        # 方式1：尝试 ANVISA API（结构化数据）
        api_responses = self._fetch_api(since)
        if api_responses:
            responses.extend(api_responses)
            return responses

        # 方式2：降级到 gov.br 页面采集
        page_responses = self._fetch_pages(since)
        responses.extend(page_responses)

        # 按 raw_content hash 去重
        seen: dict[str, SourceResponse] = {}
        for resp in responses:
            key = self._dedup_key(resp)
            if key not in seen:
                seen[key] = resp

        return list(seen.values())

    def _fetch_api(
        self, since: datetime | None = None
    ) -> list[SourceResponse]:
        """尝试从 ANVISA API 获取结构化数据。"""
        # ANVISA 的开放数据通常在 /api/ 路径下
        api_endpoints = [
            "https://www.gov.br/anvisa/api/public/acompanhamento",
            "https://www.gov.br/anvisa/api/public/recalls",
        ]

        for endpoint in api_endpoints:
            try:
                resp = self._session.get(
                    endpoint,
                    timeout=self.TIMEOUT,
                    params={"lang": "pt-BR"} if "?" not in endpoint else {},
                )
                if resp.status_code >= 400:
                    continue

                data = self._parse_json_response(resp.content)
                if not data:
                    continue

                responses = self._parse_api_data(data, "pt")
                if responses:
                    return self._filter_by_date(responses, since)
            except Exception as exc:  # noqa: BLE001 -- fallback, swallow exceptions
                import logging

                logging.getLogger(__name__).warning(
                    "ANVISA API fetch failed for endpoint %s: %s",
                    endpoint,
                    exc,
                )
                continue

            return []

    def _fetch_pages(
        self, since: datetime | None = None
    ) -> list[SourceResponse]:
        """从 ANVISA 网页采集召回数据。"""
        responses: list[SourceResponse] = []

        # ANVISA 主要召回页面路径
        page_paths = [
            "/pt-br/assuntos/assuntos-relacionados/medicamentos/recall-medicamentos",
            "/pt-br/assuntos/assuntos-relacionados/alimentos/recall-alimentos",
            "/pt-br/assuntos/assuntos-relacionados/produtos-para-saude/recall-produtos",
        ]

        for path in page_paths:
            url = self.BASE_URL + path
            page_responses = self._fetch_page(url, "pt", since)
            responses.extend(page_responses)
            time.sleep(1)  # 礼貌限速

        return responses

    def _fetch_page(
        self, url: str, lang: str, since: datetime | None = None
    ) -> list[SourceResponse]:
        """抓取单个页面，提取召回条目。"""
        try:
            resp = self._session.get(url, timeout=self.TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — 外部调用兜底,刻意吞异常
            return [
                SourceResponse(
                    source_id=self.source_id,
                    url=url,
                    raw_content=b"",
                    status="error",
                    error_msg=f"fetch failed: {exc!s}",
                    language=lang,
                )
            ]

        return self._extract_items_from_html(resp.text, url, lang)

    def _extract_items_from_html(
        self, html: str, base_url: str, lang: str
    ) -> list[SourceResponse]:
        """从 HTML 页面中提取召回条目（BeautifulSoup-free 实现）。"""
        responses = []

        # 使用正则提取结构化数据块
        # ANVISA 页面通常包含 JSON-LD 或结构化数据
        json_ld_pattern = re.compile(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )

        for match in json_ld_pattern.finditer(html):
            try:
                import json

                data = json.loads(match.group(1))
                items = self._normalize_json_ld(data)
                for item in items:
                    resp = self._item_to_response(item, lang)
                    responses.append(resp)
            except (json.JSONDecodeError, ValueError):
                continue

        # 如果没有 JSON-LD，尝试从 HTML 列表中提取
        if not responses:
            item_pattern = re.compile(
                r'<article[^>]*class=["\'][^"\']*recall[^"\']*["\'][^>]*>(.*?)</article>',
                re.DOTALL | re.IGNORECASE,
            )
            title_pattern = re.compile(
                r'<h[23][^>]*>\s*<a[^>]*>(.*?)</a>',
                re.DOTALL | re.IGNORECASE,
            )
            date_pattern = re.compile(
                r'(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})',
            )

            for match in item_pattern.finditer(html):
                article_html = match.group(1)
                title_match = title_pattern.search(article_html)
                date_match = date_pattern.search(article_html)

                title = title_match.group(1) if title_match else ""
                title = re.sub(r'<[^>]+>', "", title).strip()

                date_str = date_match.group(1) if date_match else None

                responses.append(
                    SourceResponse(
                        source_id=self.source_id,
                        url=base_url,
                        raw_content=article_html.encode("utf-8"),
                        title=title,
                        published_at=self._normalize_date_pt(date_str) if date_str else None,
                        language=lang,
                        status="ok",
                    )
                )

        return responses

    def _normalize_json_ld(self, data: Any) -> list[dict[str, Any]]:
        """规范化 JSON-LD 数据（可能返回列表或单个对象）。"""
        if isinstance(data, list):
            items = []
            for item in data:
                items.extend(self._normalize_json_ld(item))
            return items
        if isinstance(data, dict):
            # 检查是否是 @graph 结构
            if "@graph" in data:
                return self._normalize_json_ld(data["@graph"])
            # 检查 @type
            item_type = data.get("@type", "")
            if isinstance(item_type, list):
                item_type = " ".join(item_type)
            if "recall" in item_type.lower() or "product" in item_type.lower():
                return [data]
            # 检查嵌套
            for key in ("itemListElement", "item", "elements"):
                if key in data:
                    return self._normalize_json_ld(data[key])
        return []

    def _parse_json_response(self, content: bytes) -> list[dict[str, Any]]:
        """解析 JSON 响应（支持多种包装结构）。"""
        import json

        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("results", "data", "items", "records", "content"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                # 有时候数据直接在根对象中
                if "id" in data or "title" in data:
                    return [data]
            return []
        except json.JSONDecodeError:
            return []

    def _parse_api_data(
        self, data: list[dict[str, Any]], lang: str
    ) -> list[SourceResponse]:
        """将 API 数据列表转换为 SourceResponse 列表。"""
        responses = []
        for item in data:
            resp = self._item_to_response(item, lang)
            responses.append(resp)
        return responses

    def _item_to_response(
        self, item: dict[str, Any], lang: str
    ) -> SourceResponse:
        """将单个条目（API 或 JSON-LD）转换为 SourceResponse。"""
        title = self._extract_field(
            item,
            ["title", "name", "productName", "nome-produto", "product_name"],
        )
        raw_content = self._extract_field(
            item,
            [
                "raw_content",
                "description",
                "hazard_summary",
                "descriptionText",
                "descricao",
                "resumo",
                "text",
            ],
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
        url = self._extract_url(item, lang)

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
        """从 item 中按优先级查找字段（兼容葡萄牙语字段名）。"""
        for key in keys:
            val = item.get(key, "")
            if val:
                return str(val).strip()
        return ""

    def _extract_date(self, item: dict[str, Any], lang: str) -> str | None:
        """提取发布日期（葡萄牙语格式支持）。"""
        date_fields = [
            "datePublished",
            "date_published",
            "publishedDate",
            "dataPublicacao",
            "data-publicacao",
            "recallDate",
            "recall_date",
            "data",
            "dateCreated",
            "createdAt",
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
        # 巴西格式 DD/MM/YYYY 或 YYYY-MM-DD
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        # 数字格式
        m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", value)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return None

    def _normalize_date_pt(self, value: str) -> str | None:
        """将葡萄牙语日期格式归一化为 YYYY-MM-DD。"""
        # 巴西格式 DD/MM/YYYY
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        return self._normalize_date(value)

    def _extract_severity(self, item: dict[str, Any], lang: str) -> str:
        """提取严重度等级（葡萄牙语映射）。"""
        sev = (
            item.get("severity", "")
            or item.get("riskLevel", "")
            or item.get("risk_level", "")
            or item.get("gravidade", "")
            or item.get("tipo", "")
            or ""
        )
        sev_lower = sev.lower().strip()
        return self.SEVERITY_MAP_PT.get(sev_lower, sev or "一般")

    def _extract_hazard(
        self, item: dict[str, Any], raw_content: bytes, lang: str
    ) -> str:
        """从 item 或 raw_content 中推断危害类型。"""
        hazard = (
            item.get("hazardType", "")
            or item.get("hazard_type", "")
            or item.get("tipoRisco", "")
            or item.get("tipo_risco", "")
            or item.get("risk", "")
            or item.get("risco", "")
        )
        if hazard:
            # 尝试翻译葡萄牙语危害类型
            hazard_lower = hazard.lower().strip()
            if hazard_lower in self.HAZARD_TRANSLATIONS:
                return self.HAZARD_TRANSLATIONS[hazard_lower]
            return hazard.strip()

        # 从 raw_content 中检测关键词
        text = raw_content.decode("utf-8", errors="ignore").lower()
        for kw in self.HAZARD_KEYWORDS_PT:
            if kw in text:
                translated = self.HAZARD_TRANSLATIONS.get(kw, kw)
                return translated.capitalize()

        # 返回葡萄牙语原文危害类型
        return "组合危险"

    def _extract_country(self, item: dict[str, Any]) -> str:
        """提取原产国。ANVISA 数据中通常是 BR（巴西）或进口国。"""
        country = (
            item.get("country", "")
            or item.get("originCountry", "")
            or item.get("origin_country", "")
            or item.get("paisOrigem", "")
            or item.get("pais", "")
        )
        if country:
            return country[:2].upper()
        return "BR"

    def _extract_manufacturer(self, item: dict[str, Any]) -> str:
        """提取制造商/召回方。"""
        return (
            item.get("manufacturer", "")
            or item.get("manufacturerName", "")
            or item.get("recallingFirm", "")
            or item.get("company", "")
            or item.get("empresa", "")
            or item.get("fabricante", "")
            or item.get("razaoSocial", "")
        ).strip()

    def _extract_product(self, item: dict[str, Any]) -> str:
        """提取产品名称。"""
        return (
            item.get("product", "")
            or item.get("productName", "")
            or item.get("product_name", "")
            or item.get("nomeProduto", "")
            or item.get("nome-produto", "")
            or item.get("description", "")
            or item.get("descricao", "")
            or item.get("name", "")
        ).strip()

    def _extract_url(self, item: dict[str, Any], lang: str) -> str:
        """提取详情页 URL。"""
        url = (
            item.get("url", "")
            or item.get("link", "")
            or item.get("href", "")
            or item.get("sameAs", "")
            or item.get("urlNoticia", "")
        )
        if url:
            if isinstance(url, list):
                url = url[0] if url else ""
            if url and not url.startswith("http"):
                url = "https://www.gov.br" + url
        return url

    def _filter_by_date(
        self, responses: list[SourceResponse], since: datetime | None
    ) -> list[SourceResponse]:
        """按时间过滤响应。"""
        if not since:
            return responses
        cutoff_iso = since.isoformat()
        return [
            resp
            for resp in responses
            if resp.published_at and resp.published_at >= cutoff_iso
        ]

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
        text_str = str(text)
        text_clean = re.sub(r"<[^>]+>", " ", text_str)
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
            "country": raw.country or "BR",
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
            "original_text": text_str,
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
        """根据文本内容推断产品类别（葡萄牙语关键词）。"""
        text_lower = text.lower()
        category_keywords = {
            "电子产品": [
                "eletrônico", "eletronico", "bateria", "carregador", "lâmpada",
                "led", "fio", "cabo", "aparelho", "device",
            ],
            "儿童用品": [
                "criança", "infantil", "bebê", "brinquedo", "berço",
                "carrinho", "bichinho",
            ],
            "食品": [
                "alimento", "comida", "carne", "laticínio", "orgânico",
                "contaminante", "bacteriano", "food", "foodstuff",
            ],
            "化妆品": [
                "cosmético", "cosmetico", "pele", "creme", "loção",
                "beleza", "perfume",
            ],
            "药品": [
                "medicamento", "fármaco", "farmaco", "remédio", "droga",
                "farmacêutico", "farmaceutico", "tablet", "cápsula",
            ],
            "医疗器械": [
                "dispositivo médico", "dispositivo medico", "implante",
                "diagnóstico", "hospitalar", "equipamento",
            ],
            "家用电器": [
                "eletrodoméstico", "cozinha", "aquecedor", "ventilador",
                "motor", "bomba", "appliance",
            ],
        }
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "普通机电"
