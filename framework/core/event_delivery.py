from dataclasses import dataclass
from typing import Any, Callable
from framework.core.events import FrameworkEvent
from framework.infrastructure.queue import RedisQueue

@dataclass(frozen=True)
class EventSchema:
    name: str
    validator: Callable[[dict[str, Any]], None]
    version: str = "1"

class EventSchemaRegistry:
    def __init__(self): self._schemas: dict[str, EventSchema] = {}
    def register(self, schema: EventSchema) -> None: self._schemas[schema.name] = schema
    def validate(self, event: FrameworkEvent) -> None:
        schema = self._schemas.get(event.name) or self._schemas.get("*")
        if schema: schema.validator(event.payload)
    def version(self, name: str) -> str | None:
        schema = self._schemas.get(name); return schema.version if schema else None

class QueuedEventPublisher:
    def __init__(self, queue: RedisQueue, schemas: EventSchemaRegistry): self.queue, self.schemas = queue, schemas
    async def publish(self, event: FrameworkEvent) -> str:
        self.schemas.validate(event)
        return await self.queue.publish("events", {"event": event.name, "event_id": event.event_id, "request_id": event.request_id, "payload": event.payload, "schema_version": self.schemas.version(event.name)})
