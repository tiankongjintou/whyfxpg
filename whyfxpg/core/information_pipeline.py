"""信息管道领域模型。

定义 WHYfxpg 从外部信息到最终归档/反馈的全链路阶段、状态与制品类型。
领域模型不依赖具体存储或运行框架，仅描述管道契约。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelineStatus(Enum):
    """整条管道的运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageStatus(Enum):
    """单个阶段的运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageArtifact:
    """阶段输入或输出的数据制品。

    Attributes:
        artifact_type: 制品类型，例如 raw_pages / events / report 等。
        payload: 实际内容（运行期可序列化为 JSON/YAML）。
        handle: 归档句柄，当制品已写入 ArchivePort 时非空。
        archived_path: 文件系统归档路径，便于人工排查。
    """

    artifact_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    handle: str | None = None
    archived_path: str | None = None


@dataclass
class PipelineStage:
    """管道中的一个阶段定义。"""

    name: str
    order: int
    description: str = ""
    input_types: list[str] = field(default_factory=list)
    output_types: list[str] = field(default_factory=list)
    max_retries: int = 0
    required: bool = True


DEFAULT_PIPELINE_STAGES: list[PipelineStage] = [
    PipelineStage(
        name="collection",
        order=0,
        description="从各监控源采集原始页面与元数据",
        output_types=["raw_pages"],
        max_retries=2,
    ),
    PipelineStage(
        name="filtering",
        order=1,
        description="去重、内容校验、来源健康度过滤",
        input_types=["raw_pages"],
        output_types=["filtered_pages"],
    ),
    PipelineStage(
        name="extraction",
        order=2,
        description="从原始内容抽取结构化的风险事件字段",
        input_types=["filtered_pages"],
        output_types=["events"],
    ),
    PipelineStage(
        name="structuring",
        order=3,
        description="补齐国别、制造商、危害类型等维度信息",
        input_types=["events"],
        output_types=["structured_events"],
    ),
    PipelineStage(
        name="distillation",
        order=4,
        description="因果推理、历史密度聚合、证据来源修正",
        input_types=["structured_events"],
        output_types=["enriched_events"],
    ),
    PipelineStage(
        name="evaluation",
        order=5,
        description="风险评分模型计算 SS/PS/RS",
        input_types=["enriched_events"],
        output_types=["scored_events"],
    ),
    PipelineStage(
        name="alerting",
        order=6,
        description="基于预警规则生成 alert_records",
        input_types=["scored_events"],
        output_types=["alerts"],
    ),
    PipelineStage(
        name="reporting",
        order=7,
        description="生成日报/周报/专题报告",
        input_types=["scored_events", "alerts"],
        output_types=["reports"],
    ),
    PipelineStage(
        name="archive",
        order=8,
        description="归档运行制品到长期存储",
        input_types=["reports", "raw_pages"],
        output_types=["archive_handles"],
    ),
]


@dataclass
class InformationPipeline:
    """一条信息管道的配置。"""

    name: str = "default"
    description: str = "进口机电产品风险评价信息管道"
    stages: list[PipelineStage] = field(
        default_factory=lambda: [s for s in DEFAULT_PIPELINE_STAGES]
    )

    def stage_by_name(self, name: str) -> PipelineStage | None:
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None

    def ordered_stages(self) -> list[PipelineStage]:
        return sorted(self.stages, key=lambda s: s.order)
