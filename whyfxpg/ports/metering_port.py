"""计量存储端口 (P04)。

把“如何计数”与限流策略分离：
- 月维度：按月累计 API 调用次数（key = 月标识，TTL 至月末）。
- 秒维度：QPS 计数（key = 秒标识，TTL 数秒）。
- 生产用 RedisMeteringAdapter，测试用 InMemoryMeteringAdapter。
"""

from abc import ABC, abstractmethod


class MeteringPort(ABC):
    """计量计数端口。"""

    @abstractmethod
    def increment_monthly(self, account_id: str, month_key: str, ttl: int) -> int:
        """月计数 +1，返回当前值；key 不存在时初始化为 1。"""
        raise NotImplementedError

    @abstractmethod
    def get_monthly(self, account_id: str, month_key: str) -> int:
        """读取当月累计计数（无记录返回 0）。"""
        raise NotImplementedError

    @abstractmethod
    def increment_second(self, account_id: str, second_key: str, ttl: int) -> int:
        """秒计数 +1（QPS），返回当前值。"""
        raise NotImplementedError
