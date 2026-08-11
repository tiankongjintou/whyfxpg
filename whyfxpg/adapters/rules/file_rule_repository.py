"""File-based rule repository adapter.

Reads and writes rules from `Config/alert_rules.yaml`. The on-disk format is the
single source of truth for production rules; the adapter provides a stable Port
seam so the rule engine can later be switched to a database-backed repository.
"""

from pathlib import Path
from typing import Any

import yaml

from whyfxpg.config.models import AlertRule, AlertRulesConfig, _asdict
from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR, ConfigLoader
from whyfxpg.ports.rule_repository import RuleRepositoryPort


class FileRuleRepositoryAdapter(RuleRepositoryPort):
    """Load and save rules from the YAML file used by the legacy system."""

    def __init__(self, config_dir: str | None = None):
        self._loader = ConfigLoader(config_dir)
        self._path = Path(
            config_dir if config_dir else str(DEFAULT_CONFIG_DIR)
        ) / "alert_rules.yaml"

    def _config(self) -> AlertRulesConfig:
        return self._loader.typed_alert_rules

    def list(self) -> list[AlertRule]:
        return list(self._config().rules)

    def load(self, rule_id: str) -> AlertRule:
        for rule in self._config().rules:
            if rule.rule_id == rule_id:
                return rule
        raise KeyError(f"Rule not found: {rule_id}")

    def save(self, rule: Any) -> None:
        if not isinstance(rule, AlertRule):
            rule = AlertRule.from_dict(rule)
        config = self._load_raw()
        rules = config.get("rules") or []
        payload = _asdict(rule)
        for i, r in enumerate(rules):
            if r.get("rule_id") == rule.rule_id:
                rules[i] = payload
                break
        else:
            rules.append(payload)
        config["rules"] = rules
        self._write_raw(config)

    def delete(self, rule_id: str) -> None:
        config = self._load_raw()
        config["rules"] = [
            r for r in (config.get("rules") or []) if r.get("rule_id") != rule_id
        ]
        self._write_raw(config)

    def _load_raw(self) -> dict:
        return self._loader.load("alert_rules.yaml")

    def _write_raw(self, config: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
        self._loader.reload("alert_rules.yaml")
