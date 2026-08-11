"""后台 Worker 入口（P06）。

定时运行完整数据采集管道（对齐路线图 §7.1 worker 服务：
``python -m whyfxpg.worker``）。

用法：:

    python -m whyfxpg.worker                 # 默认每 6 小时
    WHYFXPG_WORKER_INTERVAL_H=1 python -m whyfxpg.worker

注意：容器内以 DATABASE_URL 指向 PostgreSQL 运行。
"""

import logging
import os
import time

from whyfxpg.main import main as run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 6


def run_forever(interval_hours: int) -> None:
    """周期执行管道；单次失败不中断调度。"""
    logger.info("worker 启动: 每 %s 小时执行一次数据采集管道", interval_hours)
    while True:
        try:
            run_pipeline()
        except Exception:
            logger.exception("本次管道执行失败，稍后重试")
        time.sleep(interval_hours * 3600)


def main() -> None:
    interval = int(os.environ.get("WHYFXPG_WORKER_INTERVAL_H", DEFAULT_INTERVAL_HOURS))
    run_forever(interval)


if __name__ == "__main__":
    main()
