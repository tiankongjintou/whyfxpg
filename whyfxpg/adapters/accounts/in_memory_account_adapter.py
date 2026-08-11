"""InMemory 账户适配器（P02/P1b-01 测试替身）。

维护双索引：api_key_hash → AccountInfo 与 account_id → AccountInfo。
"""

import uuid

from whyfxpg.ports.account_port import AccountInfo, AccountPort


class InMemoryAccountAdapter(AccountPort):
    """内存账户存储：hash 与 id 双索引。"""

    def __init__(self, accounts: dict[str, AccountInfo] | None = None):
        self._by_hash: dict[str, AccountInfo] = dict(accounts or {})
        self._by_id: dict[str, AccountInfo] = {a.account_id: a for a in self._by_hash.values()}

    def add(self, api_key_hash: str, account: AccountInfo) -> None:
        self._by_hash[api_key_hash] = account
        self._by_id[account.account_id] = account

    def verify_api_key_hash(self, api_key_hash: str) -> AccountInfo | None:
        return self._by_hash.get(api_key_hash)

    def create_account(
        self,
        company_name: str,
        plan_type: str,
        api_key_hash: str,
        api_key_prefix: str,
        monthly_quota: int,
    ) -> AccountInfo:
        account = AccountInfo(
            account_id=str(uuid.uuid4()),
            company_name=company_name,
            plan_type=plan_type,
            monthly_quota=monthly_quota,
            status="active",
        )
        self.add(api_key_hash, account)
        return account

    def rotate_api_key(self, account_id: str, new_hash: str, new_prefix: str) -> bool:
        account = self._by_id.get(account_id)
        if account is None:
            return False
        # 移除旧 hash 条目
        for h, a in list(self._by_hash.items()):
            if a.account_id == account_id:
                del self._by_hash[h]
        self._by_hash[new_hash] = account
        return True

    def set_account_status(self, account_id: str, status: str) -> bool:
        account = self._by_id.get(account_id)
        if account is None:
            return False
        updated = AccountInfo(
            account_id=account.account_id,
            company_name=account.company_name,
            plan_type=account.plan_type,
            monthly_quota=account.monthly_quota,
            status=status,
        )
        self._by_id[account_id] = updated
        for h, a in list(self._by_hash.items()):
            if a.account_id == account_id:
                self._by_hash[h] = updated
        return True

    def get_account_by_id(self, account_id: str) -> AccountInfo | None:
        return self._by_id.get(account_id)
