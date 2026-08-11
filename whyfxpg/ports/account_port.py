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

    @abstractmethod
    def create_account(
        self,
        company_name: str,
        plan_type: str,
        api_key_hash: str,
        api_key_prefix: str,
        monthly_quota: int,
    ) -> AccountInfo:
        """创建账户（P1b-01）。返回新账户信息。"""
        raise NotImplementedError

    @abstractmethod
    def rotate_api_key(self, account_id: str, new_hash: str, new_prefix: str) -> bool:
        """轮换账户 API Key（P1b-01）。旧 key 哈希被覆盖即作废。"""
        raise NotImplementedError

    @abstractmethod
    def set_account_status(self, account_id: str, status: str) -> bool:
        """设置账户状态（active/disabled，P1b-01）。"""
        raise NotImplementedError

    @abstractmethod
    def get_account_by_id(self, account_id: str) -> AccountInfo | None:
        """按 id 查询账户（P1b-01）。"""
        raise NotImplementedError
