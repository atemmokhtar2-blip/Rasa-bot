from typing import Any
from framework.infrastructure.redis import RedisProvider

class CacheProvider:
    async def get(self, key: str) -> Any: raise NotImplementedError
    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None: raise NotImplementedError
    async def delete(self, key: str) -> None: raise NotImplementedError

class RedisCache(CacheProvider):
    def __init__(self, redis: RedisProvider): self.redis = redis
    async def get(self, key: str) -> str | None: return await self.redis.get(f"cache:{key}")
    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None: await self.redis.set(f"cache:{key}", str(value), ttl_seconds)
    async def delete(self, key: str) -> None: await self.redis.delete(f"cache:{key}")
