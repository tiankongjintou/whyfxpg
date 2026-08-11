"""WHYfxpg 端到端流水线入口。

该模块提供 `main()` 函数，依次执行：
采集 → 抽取 → 评分 → 预警 → 报告 → 归档。
它会被 `scripts/run_scheduler.py` 调用，也支持直接运行：

    .venv/Scripts/python -m whyfxpg.main
"""

from pathlib import Path
from typing import Any

from whyfxpg.adapters.archive.file_system_archive import FileSystemArchiveAdapter
from whyfxpg.core.information_pipeline import InformationPipeline
from whyfxpg.services.pipeline_orchestrator import (
    PipelineOrchestrator,
    build_default_stage_runners,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "Config"
DEFAULT_ARCHIVE_DIR = PROJECT_ROOT / "whyfxpg" / "archive"
DEFAULT_DB_PATH = PROJECT_ROOT / "whyfxpg" / "data" / "whyfxpg.db"


def main(
    config_dir: str | None = None,
    db_path: str | None = None,
    archive_dir: str | None = None,
    report_output_dir: str | None = None,
) -> dict[str, Any]:
    """运行一次完整的 WHYfxpg 流水线。

    Args:
        config_dir: 配置文件目录，默认项目根目录下的 ``Config``。
        db_path: SQLite 数据库路径，默认 ``whyfxpg/data/whyfxpg.db``。
        archive_dir: 归档目录，默认 ``whyfxpg/archive``。
        report_output_dir: 报告输出目录，不填则使用 ReportGenerator 默认目录。

    Returns:
        包含 ``run_id``、``status``、``errors``、``artifacts``、``archived_path`` 的字典。
    """
    config_dir = config_dir or str(DEFAULT_CONFIG_DIR)
    db_path = db_path or str(DEFAULT_DB_PATH)
    archive_dir = archive_dir or str(DEFAULT_ARCHIVE_DIR)

    pipeline = InformationPipeline(name="whyfxpg_default")
    archive_port = FileSystemArchiveAdapter(archive_dir)

    orchestrator = PipelineOrchestrator(
        pipeline=pipeline,
        stage_runners=build_default_stage_runners(
            config_dir=config_dir,
            db_path=db_path,
        ),
        archive_port=archive_port,
        db_path=db_path,
    )

    return orchestrator.run(
        params={
            "config_dir": config_dir,
            "report_output_dir": report_output_dir,
        }
    )


if __name__ == "__main__":
    import json
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    result = main()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
