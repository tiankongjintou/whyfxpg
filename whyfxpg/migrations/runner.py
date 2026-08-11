"""轻量级数据库迁移运行器。

规则：
- 每个迁移是一个文件：`whyfxpg/migrations/NNN_description.sql` 或 `.py`。
- `.sql` 文件可包含多条语句，按分号拆分（忽略空语句与 `--` 注释）。
- `.py` 文件必须暴露 `run(conn: sqlite3.Connection) -> None`。
- 已执行版本记录在 `schema_migrations` 表，重复运行幂等。
- 单条迁移成功即记录版本；失败抛出异常，不继续后续迁移。
"""

import importlib.util
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path


class MigrationRunner:
    def __init__(
        self,
        connection: sqlite3.Connection,
        migrations_dir: Path | None = None,
    ):
        self.conn = connection
        self.migrations_dir = migrations_dir or DEFAULT_MIGRATIONS_DIR

    @staticmethod
    def default_migrations_dir() -> Path:
        return DEFAULT_MIGRATIONS_DIR

    def _ensure_migrations_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _discover_migrations(self) -> list[Migration]:
        if not self.migrations_dir.exists():
            return []
        files = sorted(
            list(self.migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))
            + list(self.migrations_dir.glob("[0-9][0-9][0-9]_*.py"))
        )
        migrations = []
        for f in files:
            version = f.name[:3]
            name = f.name[4:].split(".")[0]
            migrations.append(Migration(version=version, name=name, path=f))
        return migrations

    def _load_applied_versions(self) -> set[str]:
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        if cur.fetchone() is None:
            return set()
        cur = self.conn.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}

    @staticmethod
    def _split_sql_statements(sql_text: str) -> list[str]:
        statements = []
        for raw in sql_text.split(";"):
            stmt = raw.strip()
            if not stmt:
                continue
            # 忽略整行注释（简单处理：每条语句去掉行首 -- 注释）
            cleaned = "\n".join(
                line for line in stmt.splitlines() if not line.strip().startswith("--")
            ).strip()
            if cleaned:
                statements.append(cleaned)
        return statements

    def _apply_migration(self, migration: Migration) -> None:
        if migration.path.suffix == ".sql":
            sql_text = migration.path.read_text(encoding="utf-8")
            for stmt in self._split_sql_statements(sql_text):
                self.conn.execute(stmt)
        elif migration.path.suffix == ".py":
            spec = importlib.util.spec_from_file_location(
                f"migration_{migration.version}", migration.path
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(f"无法加载迁移模块: {migration.path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            run = getattr(module, "run", None)
            if run is None:
                raise RuntimeError(f"迁移 {migration.path} 缺少 run(conn) 函数")
            run(self.conn)
        else:
            raise RuntimeError(f"不支持的迁移类型: {migration.path.suffix}")

        self.conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            (migration.version,),
        )

    def run(self, target: str | None = None) -> list[str]:
        """执行所有未应用的迁移（或直到 target 版本）。返回已应用的版本列表。"""
        self._ensure_migrations_table()
        applied = self._load_applied_versions()
        migrations = self._discover_migrations()
        executed: list[str] = []
        for migration in migrations:
            if migration.version in applied:
                continue
            if target is not None and migration.version > target:
                break
            self._apply_migration(migration)
            executed.append(migration.version)
        return executed

    def pending(self) -> list[Migration]:
        """返回尚未应用的迁移列表（不执行）。"""
        self._ensure_migrations_table()
        applied = self._load_applied_versions()
        return [m for m in self._discover_migrations() if m.version not in applied]
