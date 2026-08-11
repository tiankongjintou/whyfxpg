"""Rule compilation and evaluation port.

A rule is a declarative configuration that is compiled into a CompiledRule,
and then evaluated against a RuleContext to produce a RuleOutcome.

This module keeps the rule engine domain model independent of the underlying
store technology (SQLite, Pandas, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RuleContext:
    """Execution context for a rule evaluation.

    Attributes:
        store: A concrete store implementation (e.g. AlertStore) for the SQLite compiler.
        now: Reference time for the evaluation. Defaults to datetime.now().  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
        fixture: A pandas DataFrame or list of dicts used by the Pandas compiler for sandboxing.
    """

    store: Any = None
    now: datetime = field(default_factory=datetime.now)
    fixture: Any | None = None


@dataclass
class QueryPlan:
    """Human- and machine-readable summary of how a rule will be evaluated."""

    operation: str = ""
    source: str = ""
    filters: list[dict[str, Any]] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    aggregations: dict[str, Any] = field(default_factory=dict)
    having: dict[str, Any] | None = None
    order_by: list[str] | None = None
    limit: int | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "source": self.source,
            "filters": self.filters,
            "group_by": self.group_by,
            "aggregations": self.aggregations,
            "having": self.having,
            "order_by": self.order_by,
            "limit": self.limit,
            "description": self.description,
        }


@dataclass
class CompiledRule:
    rule_id: str = ""
    version_id: str = ""
    rule: Any = None
    query_plan: QueryPlan = field(default_factory=QueryPlan)
    compiled_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "version_id": self.version_id,
            "compiled_at": self.compiled_at.isoformat(),
            "query_plan": self.query_plan.to_dict(),
        }


@dataclass
class RuleOutcome:
    rule_id: str = ""
    version_id: str = ""
    triggered: bool = False
    matched_rows: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    query_plan: Any = None
    natural_language_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        plan = self.query_plan
        plan_dict = plan.to_dict() if isinstance(plan, QueryPlan) else plan
        return {
            "rule_id": self.rule_id,
            "version_id": self.version_id,
            "triggered": self.triggered,
            "matched_count": len(self.matched_rows),
            "facts": self.facts,
            "query_plan": plan_dict,
            "natural_language_summary": self.natural_language_summary,
        }


@dataclass
class SandboxResult:
    rule_id: str = ""
    outcome: RuleOutcome | None = None
    duration_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class RuleCompilerPort(ABC):
    """Port for compiling a rule and evaluating it against a context."""

    @abstractmethod
    def compile(self, rule: Any) -> CompiledRule:
        """Compile a rule into an executable representation."""
        ...

    @abstractmethod
    def evaluate(self, compiled: CompiledRule, context: RuleContext) -> RuleOutcome:
        """Evaluate a compiled rule against a context and return the outcome."""
        ...
