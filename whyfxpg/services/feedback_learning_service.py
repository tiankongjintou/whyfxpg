"""Feedback learning service: close the human-review -> model-update loop.

After a human reviewer confirms or overrides a risk level, this service:

1. Runs the existing `FeedbackLearner` to compute adjustments.
2. Persists adjusted country/product factors back to `risk_model.yaml` through
   the same `ConfigurationAdminService` seam used by the admin UI.
3. Updates causal node risk scores for manufacturer/category adjustments.
4. Writes an audit-log entry.
5. Invalidates affected risk-event scores and triggers a re-score via
   `RiskEvaluationRunner`.
"""

import json
from pathlib import Path
from typing import Any

from whyfxpg.adapters.config.file_config_store import FileConfigStoreAdapter
from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR
from whyfxpg.core.feedback_learner import FeedbackLearner
from whyfxpg.core.risk_evaluation_runner import RiskEvaluationRunner
from whyfxpg.core.stores import UnitOfWork
from whyfxpg.core.stores.archive_store import AuditLogStore
from whyfxpg.services.admin.configuration_admin_service import (
    ConfigurationAdminService,
)


class FeedbackLearningService:
    """Application service that turns manual reviews into model updates."""

    DEFAULT_MODEL_ID = "default"

    def __init__(
        self,
        db_path: str | None = None,
        config_dir: str | None = None,
        admin_service: ConfigurationAdminService | None = None,
    ):
        self.db_path = db_path
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self._store = FileConfigStoreAdapter(self.config_dir)
        self._admin = admin_service or ConfigurationAdminService(
            store=self._store,
            db_path=self.config_dir / "config_objects.db",
        )
        self._learner = FeedbackLearner(
            config_dir=str(self.config_dir),
            db_path=self.db_path,
        )
        self._runner = RiskEvaluationRunner(
            config_dir=str(self.config_dir),
            db_path=self.db_path,
        )

    def learn_and_apply(
        self,
        publish: bool = True,
        actor: str = "feedback_learner",
    ) -> dict[str, Any]:
        """Learn from all pending manual reviews and apply adjustments."""
        record = self._admin.get("model", self.DEFAULT_MODEL_ID)
        if record is None:
            # Fall back to direct loader so an existing risk_model.yaml works
            # even before it has been registered as a config object.
            from whyfxpg.core.config_loader import ConfigLoader

            current_config = ConfigLoader(str(self.config_dir)).risk_model
        else:
            current_config = record.payload

        result = self._learner.learn(current_config)

        if result.get("status") != "success":
            return result

        before = json.dumps(current_config, ensure_ascii=False, sort_keys=True)
        new_config = result.get("yaml_config", current_config)
        after = json.dumps(new_config, ensure_ascii=False, sort_keys=True)

        if after != before:
            record = self._admin.update(
                "model",
                self.DEFAULT_MODEL_ID,
                new_config,
                updated_by=actor,
            )
            if publish:
                self._admin.publish("model", self.DEFAULT_MODEL_ID, published_by=actor)

        self._write_audit(
            actor=actor,
            action="feedback_learning_applied",
            target_id=self.DEFAULT_MODEL_ID,
            before_value=before,
            after_value=after,
            reason=result.get("message", ""),
        )

        self._invalidate_affected_scores(result)
        self._runner.run()

        return {
            **result,
            "published": publish and after != before,
            "model_object_id": self.DEFAULT_MODEL_ID,
        }

    def on_review_submitted(self, review_record: dict[str, Any]) -> dict[str, Any]:
        """Hook called after a manual review is submitted.

        Triggering learning on every review is acceptable for this single-tenant
        tool; for high-volume deployments, switch to a scheduled/queued learner.
        """
        return self.learn_and_apply(actor=f"review:{review_record.get('review_id', 'unknown')}")

    def _write_audit(
        self,
        actor: str,
        action: str,
        target_id: str,
        before_value: str,
        after_value: str,
        reason: str,
    ) -> None:
        with UnitOfWork(self.db_path) as uow:
            audit = AuditLogStore(uow)
            audit.write(
                actor=actor,
                action=action,
                target_type="model",
                target_id=target_id,
                before_value=before_value,
                after_value=after_value,
                reason=reason,
            )

    def _invalidate_affected_scores(self, result: dict[str, Any]) -> None:
        """Reset scores for events that touch adjusted dimensions."""
        countries: list[str] = []
        products: list[str] = []
        manufacturers: list[str] = []

        for adj in result.get("country_learnings", []):
            name = adj.get("target")
            if name:
                countries.append(name)

        for adj in result.get("product_learnings", []):
            name = adj.get("target")
            if name:
                products.append(name)

        for adj in result.get("manufacturer_learnings", []):
            name = adj.get("target", "").split(":")[-1]
            if name:
                manufacturers.append(name)

        if not countries and not products and not manufacturers:
            return

        with UnitOfWork(self.db_path) as uow:
            cursor = uow.connection.cursor()
            if countries:
                placeholders = ",".join(["?"] * len(countries))
                cursor.execute(
                    f"""
                    UPDATE risk_events
                    SET ss_score = NULL, ps_score = NULL, total_score = NULL, rs_level = NULL, evaluated_at = NULL
                    WHERE country IN ({placeholders})
                    """,
                    tuple(countries),
                )
            if products:
                placeholders = ",".join(["?"] * len(products))
                cursor.execute(
                    f"""
                    UPDATE risk_events
                    SET ss_score = NULL, ps_score = NULL, total_score = NULL, rs_level = NULL, evaluated_at = NULL
                    WHERE product_category IN ({placeholders})
                    """,
                    tuple(products),
                )
            if manufacturers:
                placeholders = ",".join(["?"] * len(manufacturers))
                cursor.execute(
                    f"""
                    UPDATE risk_events
                    SET ss_score = NULL, ps_score = NULL, total_score = NULL, rs_level = NULL, evaluated_at = NULL
                    WHERE manufacturer IN ({placeholders})
                    """,
                    tuple(manufacturers),
                )
