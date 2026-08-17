from __future__ import annotations
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol
from framework.core.models import ProcessingContext
from framework.errors import FrameworkError

Next = Callable[[ProcessingContext], Awaitable[ProcessingContext]]

@dataclass(frozen=True, slots=True)
class MiddlewareSpec:
    name: str
    handler: Any
    priority: int = 100
    security: bool = False
    enabled: bool = True
    scope: str = "global"
    project_id: str | None = None

class ProcessingMiddleware(Protocol):
    async def __call__(self, context: ProcessingContext, next_handler: Next) -> ProcessingContext: ...

class MiddlewarePipeline:
    def __init__(self): self._items: dict[str, MiddlewareSpec] = {}
    def register(self, name: str, handler: Any, *, priority: int = 100, security: bool = False, scope: str = "global", project_id: str | None = None, override: bool = False) -> None:
        if name in self._items and not override: raise ValueError(f"Middleware already registered: {name}")
        self._items[name] = MiddlewareSpec(name, handler, priority, security, True, scope, project_id)
    def unregister(self, name: str) -> None: self._items.pop(name, None)
    def list(self) -> list[MiddlewareSpec]: return sorted(self._items.values(), key=lambda item: item.priority)
    async def run(self, context: ProcessingContext, terminal: Next) -> ProcessingContext:
        selected = [item for item in self.list() if item.enabled and (item.scope == "global" or (item.scope == "project" and item.project_id == context.message.project_id))]
        async def invoke(index: int, current: ProcessingContext) -> ProcessingContext:
            if index == len(selected): return await terminal(current)
            spec = selected[index]; started = time.perf_counter()
            async def next_handler(value): return await invoke(index + 1, value)
            try:
                result = spec.handler(current, next_handler)
                if inspect.isawaitable(result): result = await result
                current.timings[f"middleware:{spec.name}"] = (time.perf_counter() - started) * 1000
                return result
            except Exception:
                if spec.security: raise
                current.metadata.setdefault("middleware_errors", []).append(spec.name)
                return await invoke(index + 1, current)
        return await invoke(0, context)

class ProcessingMiddlewareChain(MiddlewarePipeline):
    def __init__(self, middlewares: list[ProcessingMiddleware] | None = None):
        super().__init__()
        for index, middleware in enumerate(middlewares or []): self.register(getattr(middleware, "name", middleware.__class__.__name__), middleware, priority=index)

class ValidationMiddleware:
    name = "validation"
    async def __call__(self, context: ProcessingContext, next_handler: Next) -> ProcessingContext:
        if not context.message.project_id or not context.message.user_id: raise ValueError("project_id and user_id are required")
        return await next_handler(context)

class ProjectMiddleware:
    name = "project"
    def __init__(self, resolver=None): self.resolver = resolver
    async def __call__(self, context: ProcessingContext, next_handler: Next) -> ProcessingContext:
        if self.resolver: context.project = await self.resolver(context.message.project_id)
        return await next_handler(context)

class RequestLoggingMiddleware:
    name = "request_logging"
    def __init__(self, logger): self.logger = logger
    async def __call__(self, context: ProcessingContext, next_handler: Next) -> ProcessingContext:
        result = await next_handler(context)
        self.logger.info("extension_request", extra={"request_id": context.request.request_id, "project_id": context.message.project_id, "endpoint": context.metadata.get("endpoint"), "latency_ms": context.timings.get("total")})
        return result
