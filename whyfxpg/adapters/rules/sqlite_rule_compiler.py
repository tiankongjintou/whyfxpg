"""SQLite rule compiler adapter.

Compiles AlertRule objects into a QueryPlan and evaluates them against the
SQLite database via AlertStore / UnitOfWork. This keeps the core rule engine
domain model independent of the SQL dialect used by the application.
"""

from datetime import timedelta
from typing import Any

from whyfxpg.config.models import AlertRule
from whyfxpg.ports.rule_compiler import (
    CompiledRule,
    QueryPlan,
    RuleCompilerPort,
    RuleContext,
    RuleOutcome,
)


def _parse_window(window: str) -> int:
    """将 '30d' / '365d' 等时间窗口解析为天数。"""
    return int(window.replace("d", ""))


def _canonical_type(condition_type: str) -> str:
    """将旧类型别名映射到规则引擎标准类型。"""
    mapping = {
        "count_by_dimension": "aggregate",
        "risk_level_ratio_change": "aggregate",
        "month_over_month_growth": "trend",
    }
    return mapping.get(condition_type, condition_type)


def _source_for(canonical_type: str) -> str:
    return {
        "risk_level_change": "product_risk_summary",
    }.get(canonical_type, "risk_events")


def _filters_for(rule: AlertRule, canonical_type: str) -> list[dict[str, Any]]:
    condition = rule.condition or {}
    if canonical_type == "risk_level_change":
        return [
            {
                "field": "updated_at",
                "op": "gte",
                "value": f"now-{condition.get('window', '30d')}",
            },
            {
                "field": "latest_rs_level",
                "op": "in",
                "value": condition.get("to", ["M", "S"]),
            },
        ]
    if canonical_type == "threshold":
        return [
            {
                "field": "severity_level",
                "op": "in",
                "value": condition.get("values", []),
            }
        ]
    if canonical_type in ("aggregate", "trend", "novel_pattern"):
        window = condition.get("window") or condition.get("lookback", "30d")
        dim = condition.get("dimension", "")
        filters = [
            {
                "field": "publish_date",
                "op": "gte",
                "value": f"now-{window}",
            }
        ]
        if dim and canonical_type in ("aggregate", "trend"):
            filters.append({"field": dim, "op": "not_null"})
        return filters
    return []


def _group_by_for(rule: AlertRule, canonical_type: str) -> list[str]:
    condition = rule.condition or {}
    if canonical_type == "aggregate":
        return [condition.get("dimension", "")]
    if canonical_type == "trend":
        return [condition.get("dimension", "")]
    if canonical_type == "novel_pattern":
        return [
            condition.get("group_by", "product_category"),
            condition.get("dimension", ""),
        ]
    return []


def _aggregations_for(rule: AlertRule, canonical_type: str) -> dict[str, Any]:
    condition = rule.condition or {}
    original_type = condition.get("type", "")
    if canonical_type == "aggregate":
        if original_type == "risk_level_ratio_change":
            level = condition.get("level", "S")
            return {
                "total": "COUNT(*)",
                "level_count": f"SUM(CASE WHEN rs_level = '{level}' THEN 1 ELSE 0 END)",
            }
        return {"count": "COUNT(*)"}
    if canonical_type == "trend":
        return {
            "current_month_count": "COUNT(*)",
            "previous_month_count": "LAG(COUNT(*))",
        }
    return {}


def _having_for(rule: AlertRule, canonical_type: str) -> dict[str, Any] | None:
    condition = rule.condition or {}
    original_type = condition.get("type", "")
    if canonical_type == "aggregate":
        if original_type == "risk_level_ratio_change":
            return {"ratio": {"gte": condition.get("ratio_threshold", 0.0)}}
        return {"count": {"gte": condition.get("threshold", 0)}}
    if canonical_type == "trend":
        return {"growth_rate": {"gte": condition.get("growth_rate", 0.0)}}
    return None


class SqliteRuleCompilerAdapter(RuleCompilerPort):
    """Compile and evaluate rules using the application's SQLite database."""

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
        if context.store is None:
            raise ValueError("SqliteRuleCompilerAdapter requires RuleContext.store")
        rule = compiled.rule
        operation = compiled.query_plan.operation
        handler = getattr(self, f"_eval_{operation}", None)
        if handler is None:
            summary = f"规则 {rule.rule_id} 使用了未支持的编译类型 {operation}"
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
        window = condition.get("window", "30d")
        days = _parse_window(window)
        since = (context.now - timedelta(days=days)).strftime("%Y-%m-%d")
        levels = condition.get("to", ["M", "S"])
        rows = context.store.fetch_risk_level_changes(since, levels)
        return [
            {
                "object_type": "product",
                "object_value": row["product_id"],
                "triggered_value": (
                    f"level={row['latest_rs_level']}, score={row['latest_total_score']}"
                ),
                "description": f"产品风险等级上升为{row['latest_rs_level']}",
                "latest_rs_level": row["latest_rs_level"],
                "latest_total_score": row["latest_total_score"],
            }
            for row in rows
        ]

    def _eval_aggregate(self, rule: AlertRule, context: RuleContext) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        original_type = condition.get("type", "")
        if original_type == "count_by_dimension":
            return self._eval_count_by_dimension(rule, context)
        if original_type == "risk_level_ratio_change":
            return self._eval_risk_level_ratio_change(rule, context)
        # 默认按 count_by_dimension 处理，保持旧语义兼容。
        return self._eval_count_by_dimension(rule, context)

    def _eval_count_by_dimension(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        window = condition.get("window", "30d")
        threshold = condition["threshold"]
        days = _parse_window(window)
        since = (context.now - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = context.store.count_events_by_dimension(dimension, since, threshold)
        return [
            {
                "object_type": dimension,
                "object_value": row[dimension],
                "triggered_value": f"count={row['cnt']}",
                "description": (
                    f"{dimension}={row[dimension]} 在{window}内出现{row['cnt']}起事件"
                ),
                "count": row["cnt"],
            }
            for row in rows
        ]

    def _eval_risk_level_ratio_change(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        level = condition.get("level", "S")
        ratio_threshold = condition.get("ratio_threshold", 0.0)
        window = condition.get("window", "365d")
        days = _parse_window(window)
        since = (context.now - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor = context.store.uow.connection.cursor()
        cursor.execute(
            f"""
            SELECT {dimension} AS dim,
                   COUNT(*) AS total_count,
                   SUM(CASE WHEN rs_level = ? THEN 1 ELSE 0 END) AS level_count,
                   CAST(SUM(CASE WHEN rs_level = ? THEN 1 ELSE 0 END) AS REAL)
                       / NULLIF(COUNT(*), 0) AS ratio
            FROM risk_events
            WHERE publish_date >= ?
              AND {dimension} IS NOT NULL
              AND {dimension} != 'unknown'
            GROUP BY {dimension}
            HAVING ratio >= ?
            """,
            (level, level, since, ratio_threshold),
        )
        rows = cursor.fetchall()
        return [
            {
                "object_type": dimension,
                "object_value": row["dim"],
                "triggered_value": f"ratio={row['ratio']:.2f}",
                "description": (
                    f"{dimension}={row['dim']} 在{window}内 {level} 级别占比 "
                    f"{row['ratio']:.0%}"
                ),
                "total_count": row["total_count"],
                "level_count": row["level_count"],
                "ratio": row["ratio"],
            }
            for row in rows
        ]

    def _eval_threshold(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        values = condition.get("values", [])
        if not values:
            return []
        rows = context.store.fetch_high_severity_events(values, rule.rule_id)
        return [
            {
                "object_type": "event",
                "object_value": row["event_id"],
                "triggered_value": f"severity={row['severity_level']}",
                "description": f"发现{row['severity_level']}事件：{row['title']}",
                "severity_level": row["severity_level"],
                "title": row["title"],
            }
            for row in rows
        ]

    def _eval_trend(self, rule: AlertRule, context: RuleContext) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        growth_rate = condition.get("growth_rate", 0.0)
        min_events = condition.get("min_events", 1)
        window = condition.get("window", "60d")
        days = _parse_window(window)
        since = (context.now - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor = context.store.uow.connection.cursor()
        cursor.execute(
            f"""
            WITH months AS (
                SELECT strftime('%Y-%m', publish_date) AS month,
                       {dimension} AS dim,
                       COUNT(*) AS cnt
                FROM risk_events
                WHERE publish_date >= ?
                  AND {dimension} IS NOT NULL
                  AND {dimension} != 'unknown'
                GROUP BY month, dim
            )
            SELECT m1.dim,
                   m1.cnt AS current_count,
                   m2.cnt AS previous_count,
                   (m1.cnt - COALESCE(m2.cnt, 0)) * 1.0 / NULLIF(m2.cnt, 0) AS growth_rate
            FROM months m1
            LEFT JOIN months m2
                ON m2.dim = m1.dim
                AND m2.month = strftime('%Y-%m', date('now', '-1 month'))
            WHERE m1.month = strftime('%Y-%m', date('now'))
              AND m1.cnt >= ?
              AND (m2.cnt IS NULL OR (m1.cnt - m2.cnt) * 1.0 / NULLIF(m2.cnt, 0) >= ?)
            """,
            (since, min_events, growth_rate),
        )
        rows = cursor.fetchall()
        return [
            {
                "object_type": dimension,
                "object_value": row["dim"],
                "triggered_value": f"growth_rate={(row['growth_rate'] or 0):.2f}",
                "description": (
                    f"{dimension}={row['dim']} 当月 {row['current_count']} 起，"
                    f"上月 {row['previous_count'] or 0} 起，环比增长 "
                    f"{(row['growth_rate'] or 0):.0%}"
                ),
                "current_count": row["current_count"],
                "previous_count": row["previous_count"] or 0,
                "growth_rate": row["growth_rate"] or 0.0,
            }
            for row in rows
        ]

    def _eval_novel_pattern(
        self, rule: AlertRule, context: RuleContext
    ) -> list[dict[str, Any]]:
        condition = rule.condition or {}
        dimension = condition["dimension"]
        group_by = condition.get("group_by", "product_category")
        lookback = condition.get("lookback", "365d")
        days = _parse_window(lookback)
        since = (context.now - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = context.store.fetch_novel_patterns(group_by, dimension, since)
        return [
            {
                "object_type": "pattern",
                "object_value": f"{row[group_by]}|{row[dimension]}",
                "triggered_value": (
                    f"{group_by}={row[group_by]}, {dimension}={row[dimension]}"
                ),
                "description": (
                    f"在{group_by}={row[group_by]}中首次发现"
                    f"{dimension}={row[dimension]}"
                ),
            }
            for row in rows
        ]
