from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

@dataclass(slots=True)
class FrameworkEvent:
    name: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str | None = None
    trace_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    critical: bool = False
    @property
    def event_type(self) -> str: return self.name

EventHandler = Callable[[FrameworkEvent], Awaitable[None]]

class EventBus:
    def __init__(self) -> None: self._handlers: dict[str, list[EventHandler]] = {}
    def subscribe(self, event_name: str, handler: EventHandler) -> None: self._handlers.setdefault(event_name, []).append(handler)
    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_name, [])
        if handler in handlers: handlers.remove(handler)
    async def emit(self, event: FrameworkEvent) -> None:
        failures = []
        for handler in tuple(self._handlers.get(event.name, [])) + tuple(self._handlers.get("*", [])):
            try: await handler(event)
            except Exception as exc:
                failures.append(exc)
                if event.critical: raise
        if failures: event.payload.setdefault("handler_errors", [str(error) for error in failures])
