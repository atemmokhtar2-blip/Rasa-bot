import json
import time
from uuid import uuid4
import httpx
from framework.infrastructure.queue import RedisQueue
from framework.core.integrations import WebhookRegistry
from framework.infrastructure.sql import WebhookDeliveryLogORM

class WebhookDeliveryWorker:
    def __init__(self, queue: RedisQueue, timeout: float = 10.0, delivery_logs=None):
        self.queue, self.timeout, self.delivery_logs = queue, timeout, delivery_logs
        self.client = httpx.AsyncClient(timeout=timeout)
        self.running = False

    async def _log(self, job: dict, *, status_code: int | None, attempt: int, duration_ms: float, success: bool, error: str | None = None) -> None:
        if not self.delivery_logs: return
        await self.delivery_logs.save(WebhookDeliveryLogORM(id=uuid4().hex, project_id=job.get("project_id", ""), webhook_id=job.get("webhook_id", ""), event_id=job.get("event_id", ""), event_name=job.get("event", ""), status_code=status_code, attempt=attempt, duration_ms=duration_ms, success=success, error=error[:1000] if error else None))

    async def run_once(self) -> bool:
        envelope = await self.queue.consume("webhooks", timeout=1)
        if not envelope: return False
        job = envelope.get("payload", envelope)
        payload = job.get("payload", job)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        secret = job.get("secret") or envelope.get("secret")
        url = job.get("url") or envelope.get("url")
        event_id = job.get("event_id") or envelope.get("id") or ""
        attempt = int(job.get("retries", envelope.get("retries", 0))) + 1
        signature = WebhookRegistry.signature(secret, body)
        started = time.perf_counter()
        status_code = None
        try:
            response = await self.client.post(url, content=body, headers={"Content-Type": "application/json", "X-Framework-Signature": signature, "X-Framework-Event-ID": event_id})
            status_code = response.status_code
            response.raise_for_status()
            await self._log(job, status_code=status_code, attempt=attempt, duration_ms=(time.perf_counter() - started) * 1000, success=True)
        except Exception as exc:
            retries = attempt
            await self._log(job, status_code=status_code, attempt=attempt, duration_ms=(time.perf_counter() - started) * 1000, success=False, error=str(exc))
            if retries >= 3:
                await self.queue.dead_letter("webhooks", envelope, str(exc))
            else:
                job.update({"url": url, "secret": secret, "event_id": event_id, "payload": payload, "retries": retries})
                await self.queue.publish("webhooks", job)
        return True

    async def run(self) -> None:
        self.running = True
        while self.running: await self.run_once()

    def stop(self) -> None: self.running = False

    async def close(self) -> None:
        await self.client.aclose()
