"""Rule engine application service.

Orchestrates compiling and evaluating rules through pluggable ports. Keeps the
core domain thin: the rule compiler and repository adapters carry the technology
specifics, while this service provides the uniform API used by AlertEngine and
the admin/sandbox UI.
"""

import time
from typing import Any

from whyfxpg.config.models import AlertRule
from whyfxpg.ports.rule_compiler import (
    CompiledRule,
    RuleCompilerPort,
    RuleContext,
    RuleOutcome,
    SandboxResult,
)
from whyfxpg.ports.rule_repository import RuleRepositoryPort


class RuleEngine:
    """Compile, evaluate, explain, and sandbox rules."""

    def __init__(
        self,
        compiler: RuleCompilerPort | None = None,
        repository: RuleRepositoryPort | None = None,
    ):
        self.compiler = compiler
        self.repository = repository

    def compile(self, rule: Any) -> CompiledRule:
        """Compile a rule into an executable representation."""
        if self.compiler is None:
            raise RuntimeError("RuleEngine requires a compiler")
        if not isinstance(rule, AlertRule):
            rule = AlertRule.from_dict(rule)
        return self.compiler.compile(rule)

    def evaluate(
        self, compiled: CompiledRule, context: RuleContext | None = None
    ) -> RuleOutcome:
        """Evaluate a compiled rule against a context."""
        if self.compiler is None:
            raise RuntimeError("RuleEngine requires a compiler")
        if context is None:
            context = RuleContext()
        return self.compiler.evaluate(compiled, context)

    def explain(self, outcome: RuleOutcome) -> str:
        """Return a human-readable explanation of an outcome."""
        if outcome.natural_language_summary:
            return outcome.natural_language_summary
        return (
            f"规则 {outcome.rule_id} 命中 {len(outcome.matched_rows)} 条记录，"
            f"触发={outcome.triggered}"
        )

    def sandbox(self, rule: Any, fixture: Any) -> SandboxResult:
        """Evaluate a rule against an in-memory fixture for testing."""
        from whyfxpg.adapters.rules.pandas_rule_compiler import (
            PandasRuleCompilerAdapter,
        )

        start = time.perf_counter()
        try:
            if not isinstance(rule, AlertRule):
                rule = AlertRule.from_dict(rule)
            compiler = PandasRuleCompilerAdapter()
            compiled = compiler.compile(rule)
            outcome = compiler.evaluate(
                compiled, RuleContext(fixture=fixture, now=time_now())
            )
            duration_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                rule_id=compiled.rule_id,
                outcome=outcome,
                duration_ms=duration_ms,
            )
        except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
            duration_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                rule_id=getattr(rule, "rule_id", ""),
                error=str(e),
                duration_ms=duration_ms,
            )

    def list_rules(self) -> list:
        """Return all rules from the configured repository, if any."""
        if self.repository is None:
            raise RuntimeError("RuleEngine requires a repository")
        return self.repository.list()


def time_now():
    """Centralized now() for deterministic testing when monkey-patched."""
    from datetime import datetime

    return datetime.now()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计


from dataclasses import dataclass, field


def _rule_id(rule: Any) -> str:
    if isinstance(rule, dict):
        return rule.get("rule_id", "")
    return getattr(rule, "rule_id", "")


@dataclass
class RegressionReport:
    """Diff between a rule's baseline outcome and its current outcome."""

    rule_id: str
    baseline_triggered: bool
    current_triggered: bool
    baseline_count: int
    current_count: int
    diff: list[dict[str, Any]] = field(default_factory=list)
    status: str = "unchanged"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "baseline_triggered": self.baseline_triggered,
            "current_triggered": self.current_triggered,
            "baseline_count": self.baseline_count,
            "current_count": self.current_count,
            "diff": self.diff,
            "status": self.status,
        }


class RuleRegressionSuite:
    """Run a set of rules against a frozen fixture and diff against a baseline."""

    def __init__(self, compiler: RuleCompilerPort | None = None):
        self._compiler = compiler

    def _get_compiler(self) -> RuleCompilerPort:
        if self._compiler is None:
            from whyfxpg.adapters.rules.pandas_rule_compiler import (
                PandasRuleCompilerAdapter,
            )

            self._compiler = PandasRuleCompilerAdapter()
        return self._compiler

    def run(
        self,
        rules: list[Any],
        fixture: Any,
        baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate rules against a fixture and compare to baseline outcomes.

        baseline format: {rule_id: {"triggered": bool, "matched_count": int}}
        """
        baseline = baseline or {}
        reports = {}
        for rule in rules:
            rule_id = _rule_id(rule)
            compiled = self._get_compiler().compile(rule)
            outcome = self._get_compiler().evaluate(
                compiled, RuleContext(fixture=fixture, now=time_now())
            )
            base = baseline.get(rule_id, {})
            base_triggered = bool(base.get("triggered", False))
            base_count = int(base.get("matched_count", base.get("matched_rows", []).__len__() if isinstance(base, dict) else 0))
            current_count = len(outcome.matched_rows)
            status = (
                "changed"
                if base_triggered != outcome.triggered or base_count != current_count
                else "unchanged"
            )
            reports[rule_id] = RegressionReport(
                rule_id=rule_id,
                baseline_triggered=base_triggered,
                current_triggered=outcome.triggered,
                baseline_count=base_count,
                current_count=current_count,
                status=status,
            )
        return {
            "total": len(reports),
            "changed": sum(1 for r in reports.values() if r.status == "changed"),
            "unchanged": sum(1 for r in reports.values() if r.status == "unchanged"),
            "reports": {k: v.to_dict() for k, v in reports.items()},
        }
