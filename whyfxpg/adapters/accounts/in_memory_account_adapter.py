"""InMemory 账户适配器（P02 测试替身）。

按 map.md 约定“每个 Port 必须同时落地一个生产适配器 + 一个 InMemory 测试替身”。
"""


from whyfxpg.ports.account_port import AccountInfo, AccountPort


class InMemoryAccountAdapter(AccountPort):
    """内存账户存储：key 为 api_key_hash。"""

    def __init__(self, accounts: dict[str, AccountInfo] | None = None):
        self._accounts: dict[str, AccountInfo] = accounts or {}

    def add(self, api_key_hash: str, account: AccountInfo) -> None:
        self._accounts[api_key_hash] = account

    def verify_api_key_hash(self, api_key_hash: str) -> AccountInfo | None:
        return self._accounts.get(api_key_hash)
