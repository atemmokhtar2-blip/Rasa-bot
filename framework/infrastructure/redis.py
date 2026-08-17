from typing import Any
from redis.asyncio import Redis

class RedisProvider:
    def __init__(self, url: str): self.client = Redis.from_url(url, decode_responses=True)
    async def ping(self) -> bool: return bool(await self.client.ping())
    async def get(self, key: str) -> str | None: return await self.client.get(key)
    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool: return bool(await self.client.set(key, value, ex=ttl_seconds))
    async def delete(self, key: str) -> int: return int(await self.client.delete(key))
    async def incr_with_expiry(self, key: str, ttl_seconds: int) -> int:
        count = int(await self.client.incr(key))
        if count == 1: await self.client.expire(key, ttl_seconds)
        return count
    async def close(self) -> None: await self.client.aclose()
