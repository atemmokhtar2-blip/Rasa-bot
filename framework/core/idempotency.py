from __future__ import annotations
from typing import Any, Protocol
from framework.core.models import ProcessingResult

class IdempotencyStore(Protocol):
    async def get(self, key: str) -> ProcessingResult | None: ...
    async def put(self, key: str, result: ProcessingResult) -> None: ...

class InMemoryIdempotencyStore:
    def __init__(self): self._items: dict[str, ProcessingResult] = {}
    async def get(self, key: str) -> ProcessingResult | None: return self._items.get(key)
    async def put(self, key: str, result: ProcessingResult) -> None: self._items[key] = result
