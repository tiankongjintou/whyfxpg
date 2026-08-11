"""InMemory 计量适配器（P04 测试替身）。"""

import time

from whyfxpg.ports.metering_port import MeteringPort


class InMemoryMeteringAdapter(MeteringPort):
    """内存计数：key = (account_id, 维度 key)，记录 (计数, 过期时间戳)。"""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], tuple[int, float]] = {}

    def _bump(self, account_id: str, key: str, ttl: int) -> int:
        now = time.time()
        k = (account_id, key)
        count, expires = self._store.get(k, (0, 0.0))
        if now >= expires:
            count = 0
        count += 1
        self._store[k] = (count, now + ttl)
        return count

    def increment_monthly(self, account_id: str, month_key: str, ttl: int) -> int:
        return self._bump(account_id, f"m:{month_key}", ttl)

    def get_monthly(self, account_id: str, month_key: str) -> int:
        now = time.time()
        count, expires = self._store.get((account_id, f"m:{month_key}"), (0, 0.0))
        return count if now < expires else 0

    def increment_second(self, account_id: str, second_key: str, ttl: int) -> int:
        return self._bump(account_id, f"s:{second_key}", ttl)
