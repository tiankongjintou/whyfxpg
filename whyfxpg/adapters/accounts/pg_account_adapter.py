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
        return self._to_info(row)

    def create_account(
        self,
        company_name: str,
        plan_type: str,
        api_key_hash: str,
        api_key_prefix: str,
        monthly_quota: int,
    ) -> AccountInfo:
        sql = text(
            "INSERT INTO accounts "
            "(company_name, plan_type, api_key_hash, api_key_prefix, monthly_quota, status) "
            "VALUES (:name, :plan, :hash, :prefix, :quota, 'active') RETURNING "
            "id, company_name, plan_type, monthly_quota, status"
        )
        with self._engine.begin() as conn:
            row = conn.execute(
                sql,
                {
                    "name": company_name,
                    "plan": plan_type,
                    "hash": api_key_hash,
                    "prefix": api_key_prefix,
                    "quota": monthly_quota,
                },
            ).mappings().first()
        return self._to_info(row)

    def rotate_api_key(self, account_id: str, new_hash: str, new_prefix: str) -> bool:
        sql = text(
            "UPDATE accounts SET api_key_hash = :hash, api_key_prefix = :prefix "
            "WHERE id = :id"
        )
        with self._engine.begin() as conn:
            result = conn.execute(sql, {"hash": new_hash, "prefix": new_prefix, "id": account_id})
        return result.rowcount > 0

    def set_account_status(self, account_id: str, status: str) -> bool:
        sql = text("UPDATE accounts SET status = :status WHERE id = :id")
        with self._engine.begin() as conn:
            result = conn.execute(sql, {"status": status, "id": account_id})
        return result.rowcount > 0

    def get_account_by_id(self, account_id: str) -> AccountInfo | None:
        sql = text(
            "SELECT id, company_name, plan_type, monthly_quota, status "
            "FROM accounts WHERE id = :id"
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"id": account_id}).mappings().first()
        return self._to_info(row) if row else None

    @staticmethod
    def _to_info(row) -> AccountInfo:
        return AccountInfo(
            account_id=str(row["id"]),
            company_name=row["company_name"],
            plan_type=row["plan_type"],
            monthly_quota=row["monthly_quota"],
            status=row["status"],
        )

    def close(self) -> None:
        self._engine.dispose()
