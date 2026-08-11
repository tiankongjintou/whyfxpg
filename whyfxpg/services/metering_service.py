"""计量与限流服务（P04）。

额度策略（按月）与 QPS 策略（按秒）：

| plan_type | monthly | qps |
|-----------|---------|-----|
| trial     | 100     | 1   |
| basic     | 5000    | 5   |
| pro       | 50000   | 20  |
| enterprise| ∞       | ∞   |

- ``check_and_consume``：每次 API 调用扣减额度；超额抛 ``QuotaExceeded``（→ 429）。
- enterprise 无限额（仍计数，便于用量统计）。
"""

import time
from dataclasses import dataclass

from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.ports.metering_port import MeteringPort


class QuotaExceeded(Exception):
    """额度或 QPS 超限（→ 429）。"""


@dataclass(frozen=True)
class MeteringResult:
    quota_used: int
    quota_remaining: int | None  # None = 无限额


PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "trial": {"monthly": 100, "qps": 1},
    "basic": {"monthly": 5000, "qps": 5},
    "pro": {"monthly": 50000, "qps": 20},
    "enterprise": {"monthly": None, "qps": None},
}


def month_key(now: float | None = None) -> str:
    """当月标识，如 2026-08。"""
    return time.strftime("%Y-%m", time.localtime(now))


def seconds_until_month_end(now: float | None = None) -> int:
    """到月末的剩余秒数（作为月度计数 TTL）。"""
    now = time.time() if now is None else now
    lt = time.localtime(now)
    next_month = time.mktime(
        (lt.tm_year + (1 if lt.tm_mon == 12 else 0), (lt.tm_mon % 12) + 1, 1, 0, 0, 0, 0, 0, -1)
    )
    return max(int(next_month - now), 1)


class MeteringService:
    """额度扣减与用量查询。"""

    def __init__(self, metering_port: MeteringPort):
        self._port = metering_port

    def _limits(self, plan_type: str) -> dict[str, int | None]:
        return PLAN_LIMITS.get(plan_type, PLAN_LIMITS["trial"])

    def check_and_consume(self, account: AccountInfo) -> MeteringResult:
        """扣减一次调用额度；超额抛 QuotaExceeded。"""
        limits = self._limits(account.plan_type)
        monthly_limit = limits["monthly"]
        qps_limit = limits["qps"]

        used = self._port.increment_monthly(
            account.account_id, month_key(), seconds_until_month_end()
        )
        if monthly_limit is not None and used > monthly_limit:
            raise QuotaExceeded(
                f"月度额度已用尽（{used}/{monthly_limit}），请升级套餐或等待下月重置"
            )

        qps_used = self._port.increment_second(
            account.account_id, str(int(time.time())), 5
        )
        if qps_limit is not None and qps_used > qps_limit:
            raise QuotaExceeded(f"QPS 超限（{qps_used}/{qps_limit}），请降低调用频率")

        return MeteringResult(
            quota_used=used,
            quota_remaining=(monthly_limit - used) if monthly_limit is not None else None,
        )

    def get_monthly_usage(self, account_id: str) -> int:
        """当月累计调用次数。"""
        return self._port.get_monthly(account_id, month_key())

    def get_quota(self, account: AccountInfo) -> dict[str, object]:
        """额度信息（含 reset_at）。"""
        limits = self._limits(account.plan_type)
        used = self.get_monthly_usage(account.account_id)
        limit = limits["monthly"]
        remaining = (limit - used) if limit is not None else None
        reset_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds_until_month_end() + time.time()))
        return {
            "plan_type": account.plan_type,
            "monthly_limit": limit,
            "monthly_used": used,
            "monthly_remaining": remaining,
            "qps_limit": limits["qps"],
            "reset_at": reset_at,
        }
