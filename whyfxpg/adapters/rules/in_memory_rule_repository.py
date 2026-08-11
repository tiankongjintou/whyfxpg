"""In-memory rule repository adapter.

Useful for tests and sandboxing where rules should not be persisted to disk.
"""

from typing import Any

from whyfxpg.config.models import AlertRule
from whyfxpg.ports.rule_repository import RuleRepositoryPort


class InMemoryRuleRepositoryAdapter(RuleRepositoryPort):
    """Store rules in memory."""

    def __init__(self, rules: list[Any] | None = None):
        self._rules: dict[str, AlertRule] = {}
        if rules:
            for rule in rules:
                self.save(rule)

    def list(self) -> list[AlertRule]:
        return list(self._rules.values())

    def load(self, rule_id: str) -> AlertRule:
        if rule_id not in self._rules:
            raise KeyError(f"Rule not found: {rule_id}")
        return self._rules[rule_id]

    def save(self, rule: Any) -> None:
        if not isinstance(rule, AlertRule):
            rule = AlertRule.from_dict(rule)
        self._rules[rule.rule_id] = rule

    def delete(self, rule_id: str) -> None:
        self._rules.pop(rule_id, None)
