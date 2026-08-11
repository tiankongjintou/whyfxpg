"""Redis 计量适配器（P04 生产实现）。

计数使用 Redis INCR + EXPIRE（TTL 至月末 / 数秒）。
redis 依赖为生产可选（仅本模块 import 时需要）。
"""


from whyfxpg.ports.metering_port import MeteringPort


class RedisMeteringAdapter(MeteringPort):
    """基于 Redis 的计数适配器。"""

    def __init__(self, redis_url: str | None = None):
        import redis  # 延迟导入：仅生产路径需要

        self._client = redis.Redis.from_url(redis_url or "redis://localhost:6379/0")

    def _incr(self, account_id: str, kind: str, key: str, ttl: int) -> int:
        redis_key = f"whyfxpg:meter:{kind}:{account_id}:{key}"
        pipe = self._client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, ttl, nx=True)
        results = pipe.execute()
        return int(results[0])

    def increment_monthly(self, account_id: str, month_key: str, ttl: int) -> int:
        return self._incr(account_id, "m", month_key, ttl)

    def get_monthly(self, account_id: str, month_key: str) -> int:
        value = self._client.get(f"whyfxpg:meter:m:{account_id}:{month_key}")
        return int(value) if value else 0

    def increment_second(self, account_id: str, second_key: str, ttl: int) -> int:
        return self._incr(account_id, "s", second_key, ttl)
