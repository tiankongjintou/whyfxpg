"""Auto-split store module."""

import sqlite3
from typing import Self

from whyfxpg.core.db import DEFAULT_DB_PATH, get_db_connection


class UnitOfWork:
    """
    数据库连接/事务的上下文管理器。

    Usage:
        with UnitOfWork(db_path) as uow:
            store = AlertStore(uow)
            store.insert_alert(...)
    """

    def __init__(self, db_path: str | None = None):
        # None 表示使用默认数据库；与 from_connection 借用的连接区分
        self._db_path: str | None = db_path or str(DEFAULT_DB_PATH)
        self._conn: sqlite3.Connection | None = None
        self._borrowed = False

    @classmethod
    def from_connection(cls, conn: sqlite3.Connection) -> "UnitOfWork":
        """
        包装一条已存在的外部连接，形成一个不管理生命周期的 UnitOfWork。
        用于在已有事务内复用 Store，例如从 evaluate_event(event, conn) 中调用。
        """
        instance = cls.__new__(cls)
        instance._db_path = None
        instance._conn = conn
        instance._borrowed = True
        return instance

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("UnitOfWork 未进入上下文；请使用 with UnitOfWork(...) as uow:")
        return self._conn

    def __enter__(self) -> Self:
        if self._conn is None:
            self._conn = get_db_connection(self._db_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn is None:
            return
        if self._borrowed:
            # 借用外部连接，不提交/关闭
            return
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        self._conn = None


class BaseStore:
    """Store 基类：所有 store 都依附于一个已激活的 UnitOfWork。"""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow
