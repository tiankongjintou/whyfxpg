"""预警发布端口 (Phase 3C seam)。

设计决策：
- AlertEngine 与 RiskPredictor 都需要将预警写入 alert_records，但当前 AlertEngine
  自己实现去重/插入逻辑，RiskPredictor 则直接在 write_predictive_alerts 中写 SQL。
- AlertPublisher 作为统一写入 seam：调用方构造一个预警记录 dict，publisher 决定
  如何持久化、如何去重。
- 这样就把“什么是预警”与“如何写入数据库”分离，支持测试 double 与不同通道
  （DB、消息队列、邮件等）扩展。
"""

from abc import ABC, abstractmethod
from typing import Any


class AlertPublisher(ABC):
    """预警发布端口。"""

    @abstractmethod
    def publish(self, alert: dict[str, Any]) -> bool:
        """发布一条预警记录。

        Args:
            alert: 至少包含 alert_id, rule_id, rule_name, object_type,
                object_value, severity, triggered_value, description 的字典。

        Returns:
            True 表示成功写入（或本通道认为已发布）；
            False 表示因去重等原因被跳过。
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """关闭发布器资源（如需要）。"""
        raise NotImplementedError
