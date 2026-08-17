import json
from dataclasses import dataclass
from typing import Any
from redis.asyncio import Redis

@dataclass
class RedisQueue:
    redis: Redis
    prefix: str = "adf:queue"
    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        message_id = payload.get("message_id") or __import__("uuid").uuid4().hex
        envelope = {"id": message_id, "payload": payload}
        await self.redis.rpush(f"{self.prefix}:{topic}", json.dumps(envelope, default=str))
        return message_id
    async def consume(self, topic: str, timeout: int = 5) -> dict[str, Any] | None:
        item = await self.redis.blpop(f"{self.prefix}:{topic}", timeout=timeout)
        if not item: return None
        return json.loads(item[1])
    async def dead_letter(self, topic: str, envelope: dict[str, Any], reason: str) -> None:
        envelope["dead_letter_reason"] = reason
        await self.redis.rpush(f"{self.prefix}:dlq:{topic}", json.dumps(envelope, default=str))
