"""
Review service: 人工复核领域服务。

职责：
  - 把 WebUI 人工复核界面的表单提交转换为一次完整的数据库写入；
  - 在单个事务内读取当前事件状态、插入 manual_reviews、更新 risk_events.review_status；
  - 提供复核历史查询，供页面渲染使用。

页面层（whyfxpg.webui.screens.review）只负责：
  - 调用 ReviewService.submit_review(...)
  - 把返回的记录或历史列表渲染为 Streamlit 组件
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from whyfxpg.core.stores import UnitOfWork


@dataclass(frozen=True)
class ReviewSubmission:
    """人工复核提交参数。"""

    event_id: str
    reviewer: str
    reason: str
    adjusted_rs_level: str
    adjusted_ss_score: int


@dataclass(frozen=True)
class ReviewRecord:
    """一条复核记录。"""

    review_id: str
    reviewed_at: str
    event_id: str
    product_name: str | None
    country: str | None
    reviewer: str
    original_rs: str
    adjusted_rs: str
    original_ss: int
    adjusted_ss: int
    reason: str


def _severity_level_to_ss(severity_level: str | None) -> int:
    """把事件原有严重度等级映射为默认 SS 分值（用于页面 slider 默认值）。"""
    if severity_level == "高":
        return 90
    if severity_level == "中":
        return 60
    return 30


class ReviewService:
    """
    人工复核服务。

    Args:
        db_path: 数据库路径；None 时使用默认 whyfxpg.db。
    """

    def __init__(
        self,
        db_path: str | None = None,
        llm_client=None,
        feedback_service=None,
    ):
        self.db_path = db_path
        self.llm_client = llm_client
        self.feedback_service = feedback_service

    def submit_review(
        self,
        submission: ReviewSubmission,
    ) -> ReviewRecord:
        """
        提交一次人工复核。

        事务内完成：
          1. 读取事件当前 ss/ps/rs
          2. 插入 manual_reviews
          3. 将 risk_events.review_status 设为 'reviewed'
        """
        if not submission.reviewer.strip():
            raise ValueError("复核人不能为空")
        if not submission.reason.strip():
            raise ValueError("修正原因不能为空")
        if submission.adjusted_rs_level not in {"S", "M", "L", "A"}:
            raise ValueError("调整后的风险等级必须是 S/M/L/A 之一")

        with UnitOfWork(self.db_path) as uow:
            conn = uow.connection
            cursor = conn.cursor()

            # 读取当前事件状态与产品信息
            cursor.execute(
                """
                SELECT ss_score, ps_score, rs_level, product_name, country, severity_level
                FROM risk_events
                WHERE event_id = ?
                """,
                (submission.event_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"事件不存在：{submission.event_id}")

            original_ss = row["ss_score"] if row["ss_score"] is not None else _severity_level_to_ss(row["severity_level"])
            original_ps = row["ps_score"] if row["ps_score"] is not None else 50
            original_rs = row["rs_level"] or "A"
            product_name = row["product_name"]
            country = row["country"]

            review_id = str(uuid.uuid4())
            reviewed_at = datetime.now().isoformat()  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计

            cursor.execute(
                """
                INSERT INTO manual_reviews
                (review_id, event_id, reviewer, reviewed_at, action,
                 original_ss, adjusted_ss, original_ps, adjusted_ps,
                 original_rs, adjusted_rs, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    submission.event_id,
                    submission.reviewer.strip(),
                    reviewed_at,
                    "correct",
                    original_ss,
                    submission.adjusted_ss_score,
                    original_ps,
                    original_ps,
                    original_rs,
                    submission.adjusted_rs_level,
                    submission.reason.strip(),
                ),
            )

            cursor.execute(
                "UPDATE risk_events SET review_status = 'reviewed' WHERE event_id = ?",
                (submission.event_id,),
            )

        record = ReviewRecord(
            review_id=review_id,
            reviewed_at=reviewed_at,
            event_id=submission.event_id,
            product_name=product_name,
            country=country,
            reviewer=submission.reviewer.strip(),
            original_rs=original_rs,
            adjusted_rs=submission.adjusted_rs_level,
            original_ss=original_ss,
            adjusted_ss=submission.adjusted_ss_score,
            reason=submission.reason.strip(),
        )

        if self.feedback_service is not None:
            try:
                self.feedback_service.on_review_submitted(record.__dict__)
            except Exception:  # noqa: BLE001, S110 — 刻意用法(见 TD03)
                # Do not let feedback-learning failures block the review transaction.
                pass

        return record

    def confirm_alert(self, alert_id: str, reviewer: str, notes: str = "") -> None:
        """将预警标记为已确认。"""
        if not reviewer or not reviewer.strip():
            raise ValueError("复核人不能为空")
        with UnitOfWork(self.db_path) as uow:
            cursor = uow.connection.cursor()
            cursor.execute(
                """
                UPDATE alert_records
                SET status = 'confirmed', confirmed_by = ?, confirmed_at = ?, notes = ?
                WHERE alert_id = ? AND status = 'pending'
                """,
                (reviewer.strip(), datetime.now().isoformat(), notes.strip(), alert_id),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            )
            if cursor.rowcount == 0:
                raise ValueError(f"预警不存在或已处理：{alert_id}")

    def dismiss_alert(self, alert_id: str, reviewer: str, notes: str = "") -> None:
        """将预警标记为已忽略。"""
        if not reviewer or not reviewer.strip():
            raise ValueError("复核人不能为空")
        with UnitOfWork(self.db_path) as uow:
            cursor = uow.connection.cursor()
            cursor.execute(
                """
                UPDATE alert_records
                SET status = 'dismissed', confirmed_by = ?, confirmed_at = ?, notes = ?
                WHERE alert_id = ? AND status = 'pending'
                """,
                (reviewer.strip(), datetime.now().isoformat(), notes.strip(), alert_id),  # noqa: DTZ005 — 项目使用本地时间(naive),有意识设计
            )
            if cursor.rowcount == 0:
                raise ValueError(f"预警不存在或已处理：{alert_id}")

    def get_history(self, limit: int = 50) -> list[ReviewRecord]:
        """查询最近的人工复核历史。"""
        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        with UnitOfWork(self.db_path) as uow:
            conn = uow.connection
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT m.review_id, m.reviewed_at, m.event_id,
                       e.product_name, e.country,
                       m.reviewer, m.original_rs, m.adjusted_rs,
                       m.original_ss, m.adjusted_ss, m.reason
                FROM manual_reviews m
                JOIN risk_events e ON m.event_id = e.event_id
                ORDER BY m.reviewed_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        return [
            ReviewRecord(
                review_id=r["review_id"],
                reviewed_at=r["reviewed_at"],
                event_id=r["event_id"],
                product_name=r["product_name"],
                country=r["country"],
                reviewer=r["reviewer"],
                original_rs=r["original_rs"],
                adjusted_rs=r["adjusted_rs"],
                original_ss=r["original_ss"],
                adjusted_ss=r["adjusted_ss"],
                reason=r["reason"],
            )
            for r in rows
        ]

    @staticmethod
    def default_adjusted_ss_score(severity_level: str | None) -> int:
        """页面 slider 的默认值：根据当前严重度等级给出建议 SS。"""
        return _severity_level_to_ss(severity_level)
