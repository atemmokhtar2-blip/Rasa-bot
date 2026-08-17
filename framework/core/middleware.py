from __future__ import annotations
from typing import Awaitable, Callable, Protocol
from framework.core.models import ProcessingContext

Next = Callable[[ProcessingContext], Awaitable[ProcessingContext]]

class ProcessingMiddleware(Protocol):
    async def __call__(self, context: ProcessingContext, next_handler: Next) -> ProcessingContext: ...

class ValidationMiddleware:
    async def __call__(self, context: ProcessingContext, next_handler: Next) -> ProcessingContext:
        if not context.message.project_id or not context.message.user_id: raise ValueError("project_id and user_id are required")
        return await next_handler(context)

class ProjectMiddleware:
    def __init__(self, resolver=None): self.resolver = resolver
    async def __call__(self, context: ProcessingContext, next_handler: Next) -> ProcessingContext:
        if self.resolver: context.project = await self.resolver(context.message.project_id)
        return await next_handler(context)

class ProcessingMiddlewareChain:
    def __init__(self, middlewares: list[ProcessingMiddleware] | None = None): self.middlewares = middlewares or []
    async def run(self, context: ProcessingContext, terminal: Next) -> ProcessingContext:
        async def invoke(index: int, current: ProcessingContext) -> ProcessingContext:
            if index == len(self.middlewares): return await terminal(current)
            return await self.middlewares[index](current, lambda value: invoke(index + 1, value))
        return await invoke(0, context)
