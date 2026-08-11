"""Pandas / in-memory rule compiler adapter.

Compiles rules into the same QueryPlan as the SQLite adapter, but evaluates them
against an in-memory fixture (pandas DataFrame or list of dicts). This makes
rule sandboxing and unit testing independent of the production database.

If pandas is available, the fixture is converted via to_dict('records').
Otherwise a lightweight list-of-dicts implementation is used so the adapter
remains testable in minimal environments.
"""

from datetime import datetime, timedelta
from typing import Any

from whyfxpg.adapters.rules.sqlite_rule_compiler import (
    _aggregations_for,
    _canonical_type,
    _filters_for,
    _group_by_for,
    _having_for,
    _source_for,
)
from whyfxpg.config.models import AlertRule
from whyfxpg.ports.rule_compiler import (
    CompiledRule,
    QueryPlan,
    RuleCompilerPort,
    RuleContext,
    RuleOutcome,
)


def _to_records(fixture: Any) -> list[dict[str, Any]]:
    if hasattr(fixture, "to_dict"):
        return fixture.to_dict("records")
    if isinstance(fixture, list):
        return fixture
    if fixture is None:
        return []
    return [fixture]


def _month(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, str):
        return value[:7] if len(value) >= 7 else value
    return None


def _now_month(context: RuleContext) -> str:
    return context.now.strftime("%Y-%m")


def _prev_month(context: RuleContext) -> str:
    year, month = context.now.year, context.now.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _since_from_window(window: str, context: RuleContext) -> str:
    days = int(window.replace("d", ""))
    return (context.now - timedelta(days=days)).strftime("%Y-%m-%d")


class PandasRuleCompilerAdapter(RuleCompilerPort):
    """Evaluate rules against an in-memory fixture for sandboxing."""

    def compile(self, rule: AlertRule) -> CompiledRule:
        condition = rule.condition or {}
        canonical_type = _canonical_type(condition.get("type", ""))
        plan = QueryPlan(
            operation=canonical_type,
            source=_source_for(canonical_type),
            filters=_filters_for(rule, canonical_type),
            group_by=_group_by_for(rule, canonical_type),
            aggregations=_aggregations_for(rule, canonical_type),
            having=_having_for(rule, canonical_type),
            description=rule.description or rule.name,
        )
        return CompiledRule(
            rule_id=rule.rule_id,
            version_id=rule.version_id,
            rule=rule,
            query_plan=plan,
        )

    def evaluate(self, compiled: CompiledRule, context: RuleContext) -> RuleOutcome:
        if context.fixture is None:
            raise ValueError("PandasRuleCompilerAdapter requires RuleContext.fixture")
        rule = compiled.rule
        operation = compiled.query_plan.operation
        handler = getattr(self, f"_eval_{operation}", None)
        if handler is None:
            summary = f"规则 {rule.rule_id} 使用了未支持的类型 {operation}"
            return RuleOutcome(
                rule_id=rule.rule_id,
                version_id=rule.version_id,
                triggered=False,
                facts={"error": summary},
                query_plan=compiled.query_plan,
                natural_language_summary=summary,
            )
        rows = handler(rule, context)
        return RuleOutcome(
            rule_id=rule.rule_id,
            version_id=rule.version_id,
            triggered=len(rows) > 0,
            matched_rows=rows,
            facts={"matched_count": len(rows), "operation": operation},
            query_plan=compiled.query_plan,
            natural_language_summary=(
                f"规则 {rule.rule_id}（{rule.name}）命中 {len(rows)} 条记录"
            ),
        )

    def _eval_risk_level_change(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        levels = condition.get("to", ["M", "S"])
        window = condition.get("window", "30d")
        since = _since_from_window(window, context)
        records = _to_records(context.fixture)
        result = []
        for r in records:
            level = r.get("latest_rs_level")
            updated = r.get("updated_at")
            if level in levels and (updated or "") >= since:
                result.append(
                    {
                        "object_type": "product",
                        "object_value": r.get("product_id", ""),
                        "triggered_value": (
                            f"level={level}, score={r.get('latest_total_score', '')}"
                        ),
                        "description": f"产品风险等级上升为{level}",
                        "latest_rs_level": level,
                        "latest_total_score": r.get("latest_total_score"),
                    }
                )
        return result

    def _eval_aggregate(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        original_type = condition.get("type", "")
        if original_type == "risk_level_ratio_change":
            return self._eval_risk_level_ratio_change(rule, context)
        return self._eval_count_by_dimension(rule, context)

    def _eval_count_by_dimension(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        window = condition.get("window", "30d")
        threshold = condition["threshold"]
        since = _since_from_window(window, context)
        records = _to_records(context.fixture)
        counts: dict[str, int] = {}
        for r in records:
            if r.get("publish_date", "") >= since:
                counts[r.get(dimension, "")] = counts.get(r.get(dimension, ""), 0) + 1
        result = []
        for value, cnt in counts.items():
            if cnt >= threshold:
                result.append(
                    {
                        "object_type": dimension,
                        "object_value": value,
                        "triggered_value": f"count={cnt}",
                        "description": (
                            f"{dimension}={value} 在{window}内出现{cnt}起事件"
                        ),
                        "count": cnt,
                    }
                )
        return result

    def _eval_risk_level_ratio_change(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        level = condition.get("level", "S")
        ratio_threshold = condition.get("ratio_threshold", 0.0)
        window = condition.get("window", "365d")
        since = _since_from_window(window, context)
        records = _to_records(context.fixture)
        totals: dict[str, int] = {}
        levels: dict[str, int] = {}
        for r in records:
            if r.get("publish_date", "") >= since:
                value = r.get(dimension, "")
                totals[value] = totals.get(value, 0) + 1
                if r.get("rs_level") == level:
                    levels[value] = levels.get(value, 0) + 1
        result = []
        for value, total in totals.items():
            if not total:
                continue
            ratio = levels.get(value, 0) / total
            if ratio >= ratio_threshold:
                result.append(
                    {
                        "object_type": dimension,
                        "object_value": value,
                        "triggered_value": f"ratio={ratio:.2f}",
                        "description": (
                            f"{dimension}={value} 在{window}内 {level} 级别占比 "
                            f"{ratio:.0%}"
                        ),
                        "total_count": total,
                        "level_count": levels.get(value, 0),
                        "ratio": ratio,
                    }
                )
        return result

    def _eval_threshold(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        values = condition.get("values", [])
        if not values:
            return []
        records = _to_records(context.fixture)
        result = []
        for r in records:
            severity = r.get("severity_level")
            if severity in values:
                result.append(
                    {
                        "object_type": "event",
                        "object_value": r.get("event_id", ""),
                        "triggered_value": f"severity={severity}",
                        "description": f"发现{severity}事件：{r.get('title', '')}",
                        "severity_level": severity,
                        "title": r.get("title"),
                    }
                )
        return result

    def _eval_trend(self, rule: AlertRule, context: RuleContext) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        growth_rate = condition.get("growth_rate", 0.0)
        min_events = condition.get("min_events", 1)
        records = _to_records(context.fixture)
        current_month = _now_month(context)
        previous_month = _prev_month(context)
        current_counts: dict[str, int] = {}
        previous_counts: dict[str, int] = {}
        for r in records:
            month = _month(r.get("publish_date"))
            value = r.get(dimension, "")
            if month == current_month:
                current_counts[value] = current_counts.get(value, 0) + 1
            elif month == previous_month:
                previous_counts[value] = previous_counts.get(value, 0) + 1
        result = []
        for value, current in current_counts.items():
            if current < min_events:
                continue
            previous = previous_counts.get(value, 0)
            if previous == 0:
                continue
            rate = (current - previous) / previous
            if rate >= growth_rate:
                result.append(
                    {
                        "object_type": dimension,
                        "object_value": value,
                        "triggered_value": f"growth_rate={rate:.2f}",
                        "description": (
                            f"{dimension}={value} 当月 {current} 起，"
                            f"上月 {previous} 起，环比增长 {rate:.0%}"
                        ),
                        "current_count": current,
                        "previous_count": previous,
                        "growth_rate": rate,
                    }
                )
        return result

    def _eval_novel_pattern(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        group_by = condition.get("group_by", "product_category")
        lookback = condition.get("lookback", "365d")
        since = _since_from_window(lookback, context)
        records = _to_records(context.fixture)
        seen = set()
        result = []
        for r in records:
            if r.get("publish_date", "") >= since:
                key = (r.get(group_by), r.get(dimension))
                if key not in seen:
                    seen.add(key)
                    result.append(
                        {
                            "object_type": "pattern",
                            "object_value": f"{key[0]}|{key[1]}",
                            "triggered_value": (
                                f"{group_by}={key[0]}, {dimension}={key[1]}"
                            ),
                            "description": (
                                f"在{group_by}={key[0]}中首次发现"
                                f"{dimension}={key[1]}"
                            ),
                        }
                    )
        return result
