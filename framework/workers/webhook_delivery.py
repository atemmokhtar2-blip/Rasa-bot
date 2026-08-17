import httpx
from framework.infrastructure.queue import RedisQueue
from framework.core.integrations import WebhookRegistry

class WebhookDeliveryWorker:
    def __init__(self, queue: RedisQueue, timeout: float = 10.0): self.queue, self.timeout = queue, timeout
    async def run_once(self) -> bool:
        envelope = await self.queue.consume('webhooks', timeout=1)
        if not envelope: return False
        payload = envelope['payload']; body = __import__('json').dumps(payload, separators=(',', ':')).encode()
        signature = WebhookRegistry.signature(envelope['secret'], body)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(envelope['url'], content=body, headers={'Content-Type': 'application/json', 'X-Framework-Signature': signature})
                response.raise_for_status()
        except Exception as exc:
            retries = int(envelope.get('retries', 0)) + 1
            if retries >= 3: await self.queue.dead_letter('webhooks', envelope, str(exc))
            else:
                envelope['retries'] = retries
                await self.queue.publish('webhooks', payload)
        return True
