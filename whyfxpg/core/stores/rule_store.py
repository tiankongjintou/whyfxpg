"""Rule store: read-only access to configured alert rules.

Rules remain YAML-backed; this store provides a thin seam so future rule
persistence in SQLite can be swapped without touching callers.
"""

from typing import Any

from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR, ConfigLoader


class RuleStore:
    """Load and list alert rules from the config directory."""

    def __init__(self, config_dir: str | None = None):
        self.loader = ConfigLoader(config_dir) if config_dir else ConfigLoader(str(DEFAULT_CONFIG_DIR))

    def list_rules(self) -> list[dict[str, Any]]:
        """Return all configured alert rules."""
        return self.loader.alert_rules.get("rules", [])

    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        """Return a single rule by id."""
        for rule in self.list_rules():
            if rule.get("rule_id") == rule_id:
                return rule
        return None
