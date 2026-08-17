from __future__ import annotations
import asyncio
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
    event_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    @property
    def event_type(self) -> str: return self.name if "." in self.name else self.name.lower().replace("_", ".")
    def to_dict(self) -> dict[str, Any]: return {"event_id": self.event_id, "event_type": self.event_type, "event_version": self.event_version, "timestamp": self.timestamp.isoformat(), "project_id": self.project_id, "request_id": self.request_id, "trace_id": self.trace_id, "payload": self.payload, "metadata": self.metadata}

EventHandler = Callable[[FrameworkEvent], Awaitable[None]]
@dataclass(frozen=True, slots=True)
class EventSubscription:
    handler: EventHandler
    project_id: str | None = None
    priority: int = 100
    max_attempts: int = 1

class EventBus:
    def __init__(self, *, max_event_depth: int = 8) -> None: self._handlers: dict[str, list[EventSubscription]] = {}; self.max_event_depth = max_event_depth
    def subscribe(self, event_name: str, handler: EventHandler, *, project_id: str | None = None, priority: int = 100, max_attempts: int = 1) -> None:
        self._handlers.setdefault(event_name, []).append(EventSubscription(handler, project_id, priority, max(1, max_attempts)))
        self._handlers[event_name].sort(key=lambda item: item.priority)
    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name] = [item for item in self._handlers.get(event_name, []) if item.handler != handler]
    async def emit(self, event: FrameworkEvent) -> None:
        chain = list(event.metadata.get("event_chain", []))
        if len(chain) >= self.max_event_depth or event.name in chain: raise RuntimeError(f"Event recursion limit reached: {event.name}")
        event.metadata["event_chain"] = chain + [event.name]
        failures = []
        selected_handlers = list(self._handlers.get(event.name, []))
        if event.event_type != event.name: selected_handlers += list(self._handlers.get(event.event_type, []))
        selected_handlers += list(self._handlers.get("*", []))
        subscriptions = tuple(dict.fromkeys(selected_handlers))
        for subscription in subscriptions:
            if subscription.project_id is not None and subscription.project_id != event.project_id: continue
            for attempt in range(1, subscription.max_attempts + 1):
                try:
                    await subscription.handler(event); break
                except Exception as exc:
                    if attempt >= subscription.max_attempts:
                        failures.append({"handler": getattr(subscription.handler, "__name__", "handler"), "error": str(exc), "attempts": attempt})
                        if event.critical: raise
                    else: await asyncio.sleep(min(0.05 * attempt, 0.25))
        if failures: event.payload.setdefault("handler_errors", failures)
