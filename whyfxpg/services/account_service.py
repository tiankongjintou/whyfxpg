"""账户服务（P02）。

- ``verify_key(api_key)``：明文 API Key → sha256 哈希 → AccountPort 查询。
  未找到（或账户非 active）时抛 ``ApiKeyError``（由认证中间件转 403）。
- 哈希算法与 P01 accounts.api_key_hash 约定一致：sha256 hex。
"""

import hashlib

from whyfxpg.ports.account_port import AccountInfo, AccountPort


class ApiKeyError(Exception):
    """API Key 无效或账户不可用。"""


def hash_api_key(api_key: str) -> str:
    """计算 API Key 的 sha256 哈希（与 accounts.api_key_hash 存储一致）。"""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class AccountService:
    """API Key 校验服务。"""

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
