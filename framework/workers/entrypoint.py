import asyncio
from framework.config import get_settings
from framework.core.container import ApplicationContainer
from framework.infrastructure.queue import RedisQueue
from framework.infrastructure.redis import RedisProvider
from framework.workers.worker import QueueWorker

async def handle_event(payload: dict) -> None:
    container = ApplicationContainer(get_settings())
    await container.startup()
    try:
        await container.events.emit(__import__('framework.core.events', fromlist=['FrameworkEvent']).FrameworkEvent(payload.get('event', 'WORKER_EVENT'), payload))
    finally:
        await container.shutdown()

async def main() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError('REDIS_URL is required to start the worker')
    redis = RedisProvider(settings.redis_url)
    try:
        worker = QueueWorker(RedisQueue(redis.client), 'events', handle_event, settings.worker_max_retries)
        await worker.run()
    finally:
        await redis.close()

if __name__ == '__main__':
    asyncio.run(main())
