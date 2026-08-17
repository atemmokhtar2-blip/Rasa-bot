import asyncio
from framework.config import get_settings
from framework.core.container import ApplicationContainer
from framework.infrastructure.queue import RedisQueue
from framework.workers.worker import QueueWorker
from framework.workers.training import TrainingJobWorker
from framework.workers.telegram import TelegramWebhookWorker

async def handle_event(payload: dict) -> None:
    container = ApplicationContainer(get_settings())
    await container.startup()
    try:
        from framework.core.events import FrameworkEvent
        await container.events.emit(FrameworkEvent(payload.get('event', 'WORKER_EVENT'), payload))
    finally:
        await container.shutdown()

async def run_workers() -> None:
    settings = get_settings()
    if not settings.redis_url: raise RuntimeError('REDIS_URL is required to start the worker')
    if settings.database_url == 'memory://': raise RuntimeError('DATABASE_URL is required to start the worker')
    container = ApplicationContainer(settings)
    await container.startup()
    queue = RedisQueue(container.redis.client)
    event_worker = QueueWorker(queue, 'events', handle_event, settings.worker_max_retries)
    training_worker = TrainingJobWorker(queue, container.training_job_repository, container.trainer, container.model_repository)
    telegram_worker = TelegramWebhookWorker(queue, container, settings)
    try:
        await asyncio.gather(event_worker.run(), training_worker.run(), telegram_worker.run())
    finally:
        event_worker.stop(); training_worker.stop(); telegram_worker.stop()
        await container.shutdown()

async def main() -> None: await run_workers()

if __name__ == '__main__': asyncio.run(main())
