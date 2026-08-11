"""PostgreSQL 账户适配器（P02 生产实现）。

查询 accounts 表（P01 Alembic 0001 创建）：``WHERE api_key_hash = :h``。
连接串来自 ``DATABASE_URL``（见 whyfxpg.core.db.get_database_url）。
"""


from sqlalchemy import create_engine, text

from whyfxpg.core.db import get_database_url
from whyfxpg.ports.account_port import AccountInfo, AccountPort


class PgAccountAdapter(AccountPort):
    """基于 SQLAlchemy 的 accounts 表查询适配器。"""

    def __init__(self, database_url: str | None = None):
        self._url = database_url or get_database_url()
        self._engine = create_engine(self._url)

    def verify_api_key_hash(self, api_key_hash: str) -> AccountInfo | None:
        sql = text(
            "SELECT id, company_name, plan_type, monthly_quota, status "
            "FROM accounts WHERE api_key_hash = :h AND status = 'active'"
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"h": api_key_hash}).mappings().first()
        if row is None:
            return None
        return AccountInfo(
            account_id=str(row["id"]),
            company_name=row["company_name"],
            plan_type=row["plan_type"],
            monthly_quota=row["monthly_quota"],
            status=row["status"],
        )

    def close(self) -> None:
        self._engine.dispose()
