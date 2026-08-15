"""
信息抽取模块 (M3)

功能：
- 读取 raw_pages 表中 status='fetched' 的记录
- 根据 extract_rules.yaml 和 keywords.yaml 抽取结构化字段
- 写入 risk_events 表（status=auto, ss_score/ps_score 为NULL）

输入：raw_pages, extract_rules.yaml, keywords.yaml
输出：risk_events

说明：
- 本模块提供规则引擎骨架
- 可替换为更复杂的LLM抽取模块，只要输出字段遵守 risk_events 契约
"""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config.models import ExtractRule, ExtractRulesConfig
from ..config.pydantic_models import RiskModelConfig
from ..services.llm_service import LLMService
from .config_loader import DEFAULT_CONFIG_DIR, ConfigLoader
from .db import get_db_connection

# P0-2: 语言检测依赖（可选，缺失时回退为 None）
try:
    import langdetect
    _HAS_LANGDETECT = True
except ImportError:
    _HAS_LANGDETECT = False


def _rule_applies(rule: ExtractRule, source_id: str) -> bool:
    """检查规则是否对当前来源生效（空列表或含 '*' 表示全部）。"""
    if not rule.applies_to:
        return True
    return "*" in rule.applies_to or source_id in rule.applies_to


class ExtractEngine:
    """信息抽取引擎"""

    def __init__(self, config_dir: str | None = None, db_path: str | None = None,
                 llm_service: LLMService | None = None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.db_path = db_path
        self.loader = ConfigLoader(str(self.config_dir))
        self._llm_service = llm_service
        self.extract_cfg: ExtractRulesConfig = self.loader.typed_extract_rules
        self.risk_cfg: RiskModelConfig = self.loader.typed_risk_model

    @property
    def llm_service(self) -> LLMService:
        """懒加载 LLM 服务（默认读取环境变量）。"""
        if self._llm_service is None:
            self._llm_service = LLMService()
        return self._llm_service

    def get_pending_pages(self) -> list[dict[str, Any]]:
        """获取待处理的原始页面"""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM raw_pages WHERE status = 'fetched' ORDER BY fetched_at"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def apply_regex(self, text: str, patterns: list[str]) -> str | None:
        """应用正则规则抽取"""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def apply_keyword_map(self, text: str, mapping: dict[str, list[str]], default: str) -> str:
        """应用关键词映射分类"""
        text_lower = text.lower()
        for category, keywords in mapping.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    return category
        return default

    def detect_product_category(self, text: str, cfg: RiskModelConfig) -> str:
        """根据产品类别关键词匹配"""
        return self.apply_keyword_map(text, cfg.product_category_keywords, "普通机电")

    def detect_country(self, text: str, source_id: str) -> str:
        """基于国别关键词和规则推断原产国"""
        # 优先使用抽取规则中的正则
        rules = self.extract_cfg.rules
        for rule in rules:
            if rule.field_name == "country" and _rule_applies(rule, source_id):
                value = self.apply_regex(text, rule.patterns)
                if value:
                    return value
        return "unknown"

    def detect_hazard_type(self, text: str) -> str:
        """判定危害类型"""
        rules = self.extract_cfg.rules
        for rule in rules:
            if rule.field_name == "hazard_type":
                return self.apply_keyword_map(text, rule.map, rule.default or "组合危险")
        return "组合危险"

    def detect_severity_level(self, text: str) -> str:
        """判定严重度等级"""
        rules = self.extract_cfg.rules
        for rule in rules:
            if rule.field_name == "severity_level":
                return self.apply_keyword_map(text, rule.map, rule.default or "中等")
        return "中等"

    def detect_publish_date(self, text: str, default: str | None = None) -> str | None:
        """抽取发布日期"""
        rules = self.extract_cfg.rules
        for rule in rules:
            if rule.field_name == "publish_date":
                value = self.apply_regex(text, rule.patterns)
                if value:
                    # 简单归一化为 YYYY-MM-DD
                    return self.normalize_date(value)
        return default

    def normalize_date(self, value: str) -> str | None:
        """简单日期归一化"""
        # 中文
        m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        # 数字
        m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", value)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return value

    # P0-2: 语言检测
    def detect_language(self, text: str) -> str | None:
        """检测文本语言（ISO 639-1 代码，如 'en', 'zh-cn', 'ja'）。

        使用 langdetect 库（如已安装），否则返回 None。
        为提高准确性，采样前 500 个可打印字符进行检测。
        """
        if not _HAS_LANGDETECT or not text:
            return None
        sample = "".join(c for c in text[:500] if c.isprintable() and not c.isspace())
        if not sample:
            return None
        try:
            code = langdetect.detect(sample)
            # langdetect 返回 'zh-cn' 而非 'zh'，统一取前 2 位
            return code[:2] if len(code) > 2 else code
        except Exception:  # noqa: BLE001 — 外部依赖兜底,刻意吞异常
            return None

    def _llm_extract(self, text: str) -> dict[str, Any]:
        """
        LLM 抽取——使用 MiniMax 从文本中抽取结构化实体
        补充正则无法提取的字段：product_name, brand, model, hs_code,
        manufacturer, country, standards。
        """
        try:
            result = self.llm_service.extract_entities(text)
            if "error" in result and not result.get("raw"):
                return {}
            return result
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            return {"llm_error": str(e)}

    def _merge_extraction(self, regex_event: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
        """
        合并正则结果与 LLM 结果
        LLM 结果优先级更高（覆盖正则的空值或"unknown"），
        但正则已识别的关键字段（如 hazard_type, severity_level）保留。
        """
        event = regex_event.copy()
        # LLM 补充的字段：regex 结果为空/uknown 时用 LLM 填充
        llm_fields = ["product_name", "brand", "model", "hs_code",
                       "manufacturer", "country", "standards"]
        for field in llm_fields:
            regex_val = event.get(field, "") or ""
            llm_val = llm_result.get(field, "") or ""
            # 替换空值或 "unknown"
            if (not regex_val or regex_val.lower() == "unknown") and llm_val and llm_val.lower() != "unknown":
                event[field] = llm_val
        # 从 LLM 结果中提取严重度等级（更准确）
        if llm_result.get("severity_level") and llm_result["severity_level"].lower() not in ("unknown", ""):
            event["severity_level"] = llm_result["severity_level"]
        # extraction_confidence：如果 LLM 成功，提升置信度
        if "error" not in llm_result and not llm_result.get("llm_error"):
            event["extraction_confidence"] = max(event.get("extraction_confidence", 0.5), 0.8)
        return event

    def extract_event(self, page: dict[str, Any]) -> dict[str, Any] | None:
        """从单个原始页面抽取风险事件（双轨：正则 + LLM）"""
        source_id = page["source_id"]
        text = ""
        if isinstance(page["raw_content"], bytes):
            try:
                text = page["raw_content"].decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                text = ""
        else:
            text = str(page["raw_content"])

        # 简单清理
        text_clean = re.sub(r"<[^>]+>", " ", text)
        text_clean = re.sub(r"\s+", " ", text_clean)

        cfg = self.risk_cfg

        # 轨1：正则规则抽取基础字段
        event = {
            "event_id": str(uuid.uuid4()),
            "page_id": page["page_id"],
            "source_id": source_id,
            "source_url": page["url"],
            "publish_date": self.detect_publish_date(text_clean, datetime.now().strftime("%Y-%m-%d")),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            "title": page["url"],
            "product_name": "",
            "brand": "",
            "model": "",
            "hs_code": "",
            "product_category": self.detect_product_category(text_clean, cfg),
            "country": self.detect_country(text_clean, source_id),
            "manufacturer": "",
            "hazard_type": self.detect_hazard_type(text_clean),
            "hazard_desc": text_clean[:500],
            "severity_level": self.detect_severity_level(text_clean),
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
            "extracted_at": datetime.now().isoformat(),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            "evaluated_at": None,
            "config_version": "",
            "model_version": "",
            "extraction_confidence": 0.5,
            "review_status": "auto",
            "extracted_language": None,  # P0-2: 由 detect_language() 填充（轨2后可能被 LLM 结果覆盖）
        }

        # 轨2：LLM 抽取结构化实体（product_name/brand/model/hs_code/manufacturer/country/standards）
        llm_result = self._llm_extract(text_clean)
        if llm_result and "llm_error" not in llm_result:
            event = self._merge_extraction(event, llm_result)

        # P0-2: 若 LLM 未返回语言信息，用检测器填充
        if event.get("extracted_language") is None:
            event["extracted_language"] = self.detect_language(text_clean)

        return event

    def run(self) -> dict[str, Any]:
        """模块主入口"""
        pages = self.get_pending_pages()
        if not pages:
            return {
                "module": "extract_engine",
                "status": "success",
                "records_processed": 0,
                "records_created": 0,
                "errors": [],
                "message": "没有待抽取的原始页面",
            }

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        created = 0
        errors = []

        for page in pages:
            try:
                event = self.extract_event(page)
                if not event:
                    continue

                cursor.execute(
                    """
                    INSERT INTO risk_events (
                        event_id, page_id, source_id, source_url, publish_date, title,
                        product_name, brand, model, hs_code, product_category, country,
                        manufacturer, hazard_type, hazard_desc, severity_level, ss_score,
                        probability_level, ps_score, country_factor, product_factor,
                        history_factor, evidence_factor, total_score, rs_level, standards,
                        original_text, extracted_at, evaluated_at, config_version, model_version,
                        extraction_confidence, review_status, extracted_language
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_id"], event["page_id"], event["source_id"],
                        event["source_url"], event["publish_date"], event["title"],
                        event["product_name"], event["brand"], event["model"], event["hs_code"],
                        event["product_category"], event["country"], event["manufacturer"],
                        event["hazard_type"], event["hazard_desc"], event["severity_level"],
                        event["ss_score"], event["probability_level"], event["ps_score"],
                        event["country_factor"], event["product_factor"], event["history_factor"],
                        event["evidence_factor"], event["total_score"], event["rs_level"],
                        event["standards"], event["original_text"], event["extracted_at"],
                        event["evaluated_at"], event["config_version"], event["model_version"],
                        event["extraction_confidence"], event["review_status"],
                        event.get("extracted_language"),  # P0-2
                    ),
                )

                cursor.execute(
                    "UPDATE raw_pages SET status = 'parsed' WHERE page_id = ?",
                    (page["page_id"],)
                )
                created += 1
            except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                errors.append(f"{page['page_id']}: {e!s}")
                cursor.execute(
                    "UPDATE raw_pages SET status = 'failed', error_msg = ? WHERE page_id = ?",
                    (str(e), page["page_id"])
                )

        conn.commit()
        conn.close()

        return {
            "module": "extract_engine",
            "status": "success" if not errors else "partial",
            "records_processed": len(pages),
            "records_created": created,
            "errors": errors,
            "message": f"从 {len(pages)} 个页面中抽取 {created} 条风险事件",
        }


if __name__ == "__main__":
    from .db import init_db
    init_db()
    engine = ExtractEngine()
    print(engine.run())
