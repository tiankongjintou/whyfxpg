"""
预警生成模块 (M5)

功能：
- 读取 alert_rules.yaml 中的预警规则
- 读取 risk_events、product_risk_summary、country_risk_summary、enterprise_risk_summary
- 触发预警并通过 AlertPublisher 写入 alert_records

Phase 4 重构：
- 预警规则由 RuleEngine 编译和求值，AlertEngine 仅保留编排与发布职责。
- RuleEngine 通过 RuleCompilerPort 与 RuleRepositoryPort 隔离技术细节。
- 保留原有构造与入口签名，以兼容现有调用方和测试。
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..adapters.alerts.db_alert_publisher import DbAlertPublisher
from ..adapters.rules.file_rule_repository import FileRuleRepositoryAdapter
from ..adapters.rules.sqlite_rule_compiler import SqliteRuleCompilerAdapter
from ..config.models import AlertRule
from ..ports.alert_publisher import AlertPublisher
from ..ports.rule_compiler import RuleContext
from .config_loader import DEFAULT_CONFIG_DIR
from .rule_engine import RuleEngine
from .stores import AlertStore, UnitOfWork


class AlertEngine:
    """预警引擎"""

    def __init__(
        self,
        config_dir: str | None = None,
        db_path: str | None = None,
        publisher_factory: Callable[[AlertStore], AlertPublisher] | None = None,
        rule_engine: RuleEngine | None = None,
        rule_repository: Any | None = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.db_path = db_path
        self.publisher_factory = publisher_factory or DbAlertPublisher
        self.rule_repository = rule_repository or FileRuleRepositoryAdapter(
            str(self.config_dir)
        )
        self.rule_engine = rule_engine or RuleEngine(
            compiler=SqliteRuleCompilerAdapter(),
            repository=self.rule_repository,
        )

    def _publish_alert(
        self,
        publisher: AlertPublisher,
        rule: AlertRule,
        row: dict,
    ) -> bool:
        """组装并发布一条预警记录。"""
        return publisher.publish(
            {
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "object_type": row.get("object_type", "object"),
                "object_value": row.get("object_value", ""),
                "severity": rule.severity,
                "triggered_value": row.get("triggered_value", ""),
                "description": row.get("description", ""),
                "explanation_json": row.get("explanation_json"),
            }
        )

    def _run(self, store: AlertStore) -> dict[str, Any]:
        """在已提供的 store 上执行所有规则。"""
        publisher = self.publisher_factory(store)
        triggered_total = 0
        errors = []
        context = RuleContext(store=store, now=datetime.now())  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

        for rule in self.rule_repository.list():
            if not rule.enabled:
                continue
            try:
                compiled = self.rule_engine.compile(rule)
                outcome = self.rule_engine.evaluate(compiled, context)
                for row in outcome.matched_rows:
                    if self._publish_alert(publisher, rule, row):
                        triggered_total += 1
            except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
                errors.append(f"{rule.rule_id}: {e!s}")

        publisher.close()

        rules = self.rule_repository.list()
        return {
            "module": "alert_engine",
            "status": "success" if not errors else "partial",
            "records_processed": len(rules),
            "records_created": triggered_total,
            "errors": errors,
            "message": f"触发 {triggered_total} 条预警",
        }

    def run(self, uow: UnitOfWork | None = None) -> dict[str, Any]:
        """模块主入口。

        如果调用方提供已打开的 UnitOfWork，则复用其事务；
        否则自行创建并提交/关闭。
        """
        if uow is not None:
            return self._run(AlertStore(uow))

        with UnitOfWork(self.db_path) as uow_ctx:
            return self._run(AlertStore(uow_ctx))


if __name__ == "__main__":
    from .db import init_db

    init_db()
    engine = AlertEngine()
    print(engine.run())
