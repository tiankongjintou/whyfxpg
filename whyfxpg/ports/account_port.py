"""账户端口 (P02)。

把“如何校验 API Key / 读取账户”与认证流程分离：
- AccountPort 只负责按 api_key_hash 查询账户，不关心认证协议（中间件/依赖）。
- 生产用 PgAccountAdapter（查 accounts 表），测试用 InMemoryAccountAdapter。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AccountInfo:
    """账户公开信息（不含 api_key_hash / api_key_prefix 等敏感字段）。"""

    account_id: str
    company_name: str
    plan_type: str
    monthly_quota: int
    status: str


class AccountPort(ABC):
    """账户查询端口。"""

    @abstractmethod
    def verify_api_key_hash(self, api_key_hash: str) -> AccountInfo | None:
        """按 api_key 哈希查询账户。

        Args:
            api_key_hash: api_key 的哈希值（sha256 hex）。

        Returns:
            匹配的账户信息；未找到返回 None。
        """
        raise NotImplementedError
