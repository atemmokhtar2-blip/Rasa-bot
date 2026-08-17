import asyncio
from typing import Awaitable, Callable, Any
from framework.infrastructure.queue import RedisQueue

class QueueWorker:
    def __init__(self, queue: RedisQueue, topic: str, handler: Callable[[dict[str, Any]], Awaitable[None]], max_retries: int = 3):
        self.queue, self.topic, self.handler, self.max_retries = queue, topic, handler, max_retries
        self.running = False

    async def run_once(self) -> bool:
        envelope = await self.queue.consume(self.topic, timeout=1)
        if not envelope: return False
        payload = envelope["payload"]
        attempts = int(payload.get("_attempts", 0))
        try:
            await self.handler(payload)
        except Exception as exc:
            attempts += 1
            payload["_attempts"] = attempts
            if attempts >= self.max_retries:
                await self.queue.dead_letter(self.topic, envelope, str(exc))
            else:
                await asyncio.sleep(min(2 ** attempts, 30))
                await self.queue.publish(self.topic, payload)
        return True

    async def run(self) -> None:
        self.running = True
        while self.running:
            await self.run_once()
            await asyncio.sleep(0)

    def stop(self) -> None: self.running = False
