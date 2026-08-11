#!/usr/bin/env python3
"""
WHYfxpg 定时调度入口

功能：
- 按配置时间周期运行完整数据链路（python -m whyfxpg.main）
- 支持立即执行一次（--now）和后台周期运行（--interval 小时）
- 失败时打印日志并继续，不会中断调度

用法：
    .venv/Scripts/python scripts/run_scheduler.py --interval 6   # 每 6 小时跑一次
    .venv/Scripts/python scripts/run_scheduler.py --now          # 立即跑一次

注意：
- 先确保数据库已启用 WAL（python -m whyfxpg.core.db --help 或手动 init_db）
- 需要与 Web UI 同时运行时，WAL 模式可显著降低 database is locked 概率
"""

import argparse
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import schedule

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from whyfxpg.main import main as run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_once() -> int:
    """执行一次完整链路，返回退出码（0=成功，1=失败）"""
    logger.info("=" * 60)
    logger.info("调度触发：开始运行 WHYfxpg 全链路")
    logger.info("=" * 60)
    try:
        run_pipeline()
        logger.info("全链路运行成功")
        return 0
    except Exception as e:  # noqa: BLE001 — 外部调用/配置解析兜底,刻意吞异常
        logger.error("全链路运行失败: %s", e)
        logger.error(traceback.format_exc())
        return 1


def run_loop(interval_hours: int) -> None:
    """按 interval_hours 周期运行"""
    schedule.every(interval_hours).hours.do(run_once)
    logger.info("已启动定时调度，每 %d 小时运行一次，按 Ctrl+C 停止", interval_hours)

    # 首次立即执行一次，方便调试
    run_once()

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="WHYfxpg 定时调度入口")
    parser.add_argument(
        "--interval",
        type=int,
        default=6,
        help="后台运行间隔（小时），默认 6",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="仅立即执行一次，不进入后台循环",
    )
    args = parser.parse_args()

    if args.now:
        sys.exit(run_once())
    else:
        run_loop(args.interval)


if __name__ == "__main__":
    main()
