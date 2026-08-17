import asyncio
import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from framework.errors import AuthorizationError, ToolError
from framework.infrastructure.queue import RedisQueue

class ToolExecutionService:
    def __init__(self, timeout_seconds: float = 10.0): self.timeout_seconds = timeout_seconds
    async def execute(self, tool: Any, granted_permissions: set[str], **kwargs: Any) -> Any:
        required = set(getattr(tool, "required_permissions", set()))
        missing = required - granted_permissions
        if missing: raise AuthorizationError(f"Missing tool permissions: {sorted(missing)}")
        try: return await asyncio.wait_for(tool.execute(**kwargs), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc: raise ToolError(f"Tool execution timed out: {getattr(tool, 'name', 'unknown')}") from exc
        except ToolError: raise
        except Exception as exc: raise ToolError(f"Tool execution failed: {getattr(tool, 'name', 'unknown')}") from exc

@dataclass
class WebhookSubscription:
    event_name: str
    url: str
    secret: str
    timeout_seconds: float = 10.0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

class WebhookRegistry:
    def __init__(self): self._subscriptions: list[WebhookSubscription] = []
    def register(self, subscription: WebhookSubscription) -> None: self._subscriptions.append(subscription)
    def for_event(self, event_name: str) -> list[WebhookSubscription]: return [s for s in self._subscriptions if s.event_name in {event_name, "*"}]
    @staticmethod
    def signature(secret: str, body: bytes) -> str: return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

class QueuedWebhookDispatcher:
    def __init__(self, queue: RedisQueue): self.queue = queue
    async def enqueue(self, subscription: WebhookSubscription, payload: dict[str, Any]) -> str:
        return await self.queue.publish("webhooks", {"url": subscription.url, "event": subscription.event_name, "payload": payload, "secret": subscription.secret, "retries": 0})
