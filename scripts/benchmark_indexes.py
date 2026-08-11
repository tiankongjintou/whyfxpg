#!/usr/bin/env python3
"""TD02 性能验证脚本：100 万条 risk_events 下 manufacturer 查询 < 100ms。

用法（在项目根目录执行）：:

    python scripts/benchmark_indexes.py                 # 默认 100 万条,临时 SQLite
    python scripts/benchmark_indexes.py --rows 1000000 --db /tmp/bench.db
    python scripts/benchmark_indexes.py --no-index      # 对照:不带索引时的耗时

验证目标（TD02 AC-5）：
    100 万条 risk_events 记录，manufacturer 查询响应时间 < 100ms（带索引）。

说明：
- 表结构对齐 Alembic 0001/0002（risk_events 关键列 + idx_risk_events_manufacturer）。
- 批量插入（executemany），结果输出带索引/无索引对照耗时。
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
import time
from collections.abc import Iterator
from pathlib import Path

MANUFACTURERS = ["Bosch", "Makita", "DeWalt", "Black+Decker", "Hitachi", "Panasonic"]
COUNTRIES = ["德国", "日本", "美国", "中国", "意大利", "英国"]
CATEGORIES = ["电动工具", "家用厨房电器", "儿童玩具", "汽车零部件"]

CREATE_SQL = """
CREATE TABLE risk_events (
    event_id TEXT PRIMARY KEY,
    manufacturer TEXT,
    country TEXT,
    product_category TEXT,
    created_at TEXT
);
"""

INDEX_SQL = "CREATE INDEX idx_risk_events_manufacturer ON risk_events (manufacturer);"


def event_batches(n: int, batch: int = 20000) -> Iterator[list[tuple[str, str, str, str, str]]]:
    """生成 n 条测试事件,按 batch 分块。"""
    for start in range(0, n, batch):
        rows = []
        for i in range(start, min(start + batch, n)):
            rows.append(
                (
                    f"e{i:08d}",
                    random.choice(MANUFACTURERS),
                    random.choice(COUNTRIES),
                    random.choice(CATEGORIES),
                    "2026-01-01",
                )
            )
        yield rows


def main() -> int:
    parser = argparse.ArgumentParser(description="TD02 索引性能验证")
    parser.add_argument("--rows", type=int, default=1_000_000, help="数据量(默认 100 万)")
    parser.add_argument("--db", default=":memory:", help="SQLite 文件路径(默认内存)")
    parser.add_argument("--no-index", action="store_true", help="对照模式:不建索引")
    parser.add_argument("--target-ms", type=float, default=100.0, help="目标响应时间(默认 100ms)")
    args = parser.parse_args()

    db_path = args.db
    if db_path != ":memory:" and Path(db_path).exists():
        Path(db_path).unlink()

    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_SQL)
    if not args.no_index:
        conn.execute(INDEX_SQL)

    # 批量插入
    t0 = time.perf_counter()
    for batch in event_batches(args.rows):
        conn.executemany(
            "INSERT INTO risk_events (event_id, manufacturer, country, product_category, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            batch,
        )
    conn.commit()
    insert_s = time.perf_counter() - t0
    count = conn.execute("SELECT COUNT(*) FROM risk_events").fetchone()[0]

    # 查询计时(取 5 次最差值)
    times: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        conn.execute(
            "SELECT COUNT(*) FROM risk_events WHERE manufacturer = 'Bosch'"
        ).fetchone()
        times.append((time.perf_counter() - t0) * 1000)
    worst_ms = max(times)
    avg_ms = sum(times) / len(times)

    mode = "带索引" if not args.no_index else "无索引(对照)"
    print(f"数据量: {count} 行 | 插入耗时: {insert_s:.1f}s | 模式: {mode}")
    print(f"manufacturer 查询: 最差 {worst_ms:.2f}ms, 平均 {avg_ms:.2f}ms")
    conn.close()

    if args.no_index:
        print("(对照模式,不判定)")
        return 0
    ok = worst_ms < args.target_ms
    print(f"{'✅' if ok else '❌'} 目标 < {args.target_ms}ms: {'通过' if ok else '未达标'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
