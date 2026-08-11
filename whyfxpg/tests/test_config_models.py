"""类型化配置模型测试。"""


from whyfxpg.config.models import (
    AlertRulesConfig,
    ExtractRule,
    ExtractRulesConfig,
    LevelConfig,
    RiskModelConfig,
    SourceConfig,
    SourcesConfig,
)


def test_level_config_from_dict():
    level = LevelConfig.from_dict({"score": 95, "min": 90, "max": 99, "default": 95, "description": "严重"})
    assert level.score == 95
    assert level.min == 90
    assert level.description == "严重"


def test_risk_model_config_typing():
    cfg = RiskModelConfig.from_dict(
        {
            "version": "2.0",
            "severity_levels": {
                "严重": {"min": 90, "max": 99, "default": 95, "description": "严重"},
            },
            "probability_levels": {
                "可能": {"min": 60, "max": 79, "default": 70, "description": "可能"},
            },
            "risk_matrix": {
                "columns": ["L", "M", "S"],
                "rows": {"A": ["L", "M", "M"], "L": ["L", "M", "S"]},
            },
            "country_factors": {"美国": 1.2},
            "product_factors": {"电气": 1.1},
            "product_category_keywords": {"电气危险": ["电击", "触电"]},
            "history_factor": {"formula": "1 + min(count/10, 1)", "max": 2.0, "min": 1.0},
            "evidence_factors": {"图片": 1.2},
            "risk_level_thresholds": {"S": 7000},
            "score_formula": "ss_score * ps_score / 100",
        }
    )
    assert cfg.version == "2.0"
    assert "严重" in cfg.severity_levels
    assert cfg.severity_levels["严重"].default == 95
    assert cfg.risk_matrix.columns == ["L", "M", "S"]
    assert cfg.country_factors["美国"] == 1.2
    assert cfg.product_category_keywords["电气危险"] == ["电击", "触电"]
    assert cfg.history_factor.formula == "1 + min(count/10, 1)"
    assert cfg.score_formula == "ss_score * ps_score / 100"


def test_source_config_carries_id_and_defaults():
    cfg = SourceConfig.from_dict(
        "test_api",
        {
            "name": "Test API",
            "url": "https://example.com/feed",
            "enabled": False,
            "delay": 5,
            "headers": {"User-Agent": "WHYfxpg"},
        },
    )
    assert cfg.source_id == "test_api"
    assert cfg.name == "Test API"
    assert cfg.enabled is False
    assert cfg.delay == 5
    assert cfg.to_dict()["source_id"] == "test_api"


def test_sources_config_enabled_sources():
    cfg = SourcesConfig.from_dict(
        {
            "sources": {
                "api_a": {"enabled": True},
                "api_b": {"enabled": False},
                "api_c": {"enabled": True},
            }
        }
    )
    enabled_ids = {s.source_id for s in cfg.enabled_sources()}
    assert enabled_ids == {"api_a", "api_c"}


def test_alert_rules_config_enabled_rules():
    cfg = AlertRulesConfig.from_dict(
        {
            "rules": [
                {"rule_id": "r1", "enabled": True, "condition": {"type": "threshold"}},
                {"rule_id": "r2", "enabled": False, "condition": {"type": "count_by_dimension"}},
            ]
        }
    )
    assert len(cfg.enabled_rules()) == 1
    assert cfg.enabled_rules()[0].rule_id == "r1"


def test_extract_rule_applies_to_and_patterns():
    rule = ExtractRule.from_dict(
        {
            "rule_id": "country_rule",
            "field": "country",
            "applies_to": ["api_a", "api_b"],
            "patterns": [r"原产国[:：]\s*([^\s]+)"],
            "default": "unknown",
        }
    )
    assert rule.field_name == "country"
    assert "api_a" in rule.applies_to
    assert len(rule.patterns) == 1


def test_extract_rules_config_iteration():
    cfg = ExtractRulesConfig.from_dict(
        {
            "rules": [
                {"rule_id": "r1", "field": "hazard_type"},
                {"rule_id": "r2", "field": "country"},
            ]
        }
    )
    fields = [r.field_name for r in cfg.rules]
    assert fields == ["hazard_type", "country"]


def test_empty_config_safe():
    assert RiskModelConfig.from_dict(None).version == "1.0"
    assert SourcesConfig.from_dict(None).version == "1.0"
    assert AlertRulesConfig.from_dict(None).rules == []
