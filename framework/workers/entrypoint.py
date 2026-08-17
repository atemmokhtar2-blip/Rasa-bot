import asyncio
from framework.config import get_settings
from framework.core.container import ApplicationContainer
from framework.infrastructure.queue import RedisQueue
from framework.workers.worker import QueueWorker
from framework.workers.training import TrainingJobWorker
from framework.workers.telegram import TelegramWebhookWorker
from framework.workers.maintenance import MaintenanceWorker
from framework.workers.webhook_delivery import WebhookDeliveryWorker

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
    training_worker = TrainingJobWorker(queue, container.training_job_repository, container.trainer, container.model_repository, container.model_artifacts, dataset_loader=container.dataset_loader, dataset_pipeline=container.dataset_pipeline, evaluation_engine=container.evaluation)
    telegram_worker = TelegramWebhookWorker(queue, container, settings)
    maintenance_worker = MaintenanceWorker(container.audit, settings.audit_retention_days)
    webhook_worker = WebhookDeliveryWorker(queue, timeout=settings.webhook_timeout, delivery_logs=container.webhook_delivery_log_repository)
    try:
        await asyncio.gather(event_worker.run(), training_worker.run(), telegram_worker.run(), maintenance_worker.run(), webhook_worker.run())
    finally:
        event_worker.stop(); training_worker.stop(); telegram_worker.stop(); maintenance_worker.stop(); webhook_worker.stop()
        await webhook_worker.close()
        await container.shutdown()

async def main() -> None: await run_workers()

if __name__ == '__main__': asyncio.run(main())
