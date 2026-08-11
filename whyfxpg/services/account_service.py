"""账户服务（P02/P1b-01）。

- ``verify_key(api_key)``：明文 API Key → sha256 哈希 → AccountPort 查询。
  未找到（或账户非 active）时抛 ``ApiKeyError``（由认证中间件转 403）。
- 哈希算法与 P01 accounts.api_key_hash 约定一致：sha256 hex。
- P1b-01：账户生命周期（create/rotate/disable）+ master key 校验。
"""

import hashlib
import os
import secrets

from whyfxpg.ports.account_port import AccountInfo, AccountPort


class ApiKeyError(Exception):
    """API Key 无效或账户不可用。"""


class MasterKeyError(Exception):
    """Master Key 未配置或不匹配（P1b-01）。"""


def hash_api_key(api_key: str) -> str:
    """计算 API Key 的 sha256 哈希（与 accounts.api_key_hash 存储一致）。"""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class AccountService:
    """API Key 校验与账户生命周期服务。"""

    def __init__(self, account_port: AccountPort):
        self._port = account_port

    def verify_key(self, api_key: str) -> AccountInfo:
        """验证 API Key，返回账户信息；无效则抛 ApiKeyError（→ 403）。"""
        account = self._port.verify_api_key_hash(hash_api_key(api_key))
        if account is None:
            raise ApiKeyError("无效的 API Key")
        if account.status != "active":
            raise ApiKeyError("账户已停用")
        return account

    def lookup_by_hash(self, api_key_hash: str) -> AccountInfo | None:
        """按哈希直查（内部/管理用途）。"""
        return self._port.verify_api_key_hash(api_key_hash)

    # ── P1b-01: 账户生命周期 ───────────────────────────────────

    def create_account(
        self,
        company_name: str,
        plan_type: str,
        monthly_quota: int,
    ) -> tuple[AccountInfo, str]:
        """创建账户并生成 API Key（明文仅返回一次）。"""
        api_key = "whx_" + secrets.token_hex(16)
        account = self._port.create_account(
            company_name=company_name,
            plan_type=plan_type,
            api_key_hash=hash_api_key(api_key),
            api_key_prefix=api_key[:10],
            monthly_quota=monthly_quota,
        )
        return account, api_key

    def rotate_api_key(self, account_id: str) -> str:
        """轮换账户 API Key，旧 key 立即作废。"""
        new_key = "whx_" + secrets.token_hex(16)
        ok = self._port.rotate_api_key(account_id, hash_api_key(new_key), new_key[:10])
        if not ok:
            raise ApiKeyError("账户不存在")
        return new_key

    def disable_account(self, account_id: str) -> None:
        """禁用账户（后续请求 403）。"""
        self._port.set_account_status(account_id, "disabled")

    def get_account(self, account_id: str) -> AccountInfo | None:
        """按 id 查账户（管理用途）。"""
        return self._port.get_account_by_id(account_id)

    @staticmethod
    def check_master_key(request_key: str | None) -> None:
        """校验 X-Master-Key（env WHYFXPG_MASTER_KEY）。

        Raises:
            MasterKeyError: 未配置 master key（503 语义）或 key 不匹配。
        """
        expected = os.environ.get("WHYFXPG_MASTER_KEY", "")
        if not expected:
            raise MasterKeyError("WHYFXPG_MASTER_KEY 未配置，注册接口不可用")
        if request_key != expected:
            raise MasterKeyError("X-Master-Key 无效")
