from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

class Repository(Protocol):
    async def create(self, value: Any) -> Any: ...
    async def get(self, identifier: str) -> Any | None: ...
    async def list(self) -> list[Any]: ...

class InMemoryRepository:
    def __init__(self): self.items: dict[str, Any] = {}
    async def create(self, value):
        identifier = getattr(value, "id", None) or str(uuid4())
        if not getattr(value, "id", None): setattr(value, "id", identifier)
        self.items[identifier] = value
        return value
    async def get(self, identifier): return self.items.get(identifier)
    async def list(self): return list(self.items.values())

@dataclass
class ProjectRecord:
    name: str
    owner_id: str
    description: str = ""
    environment: str = "development"
    status: str = "active"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    configuration: dict = field(default_factory=dict)

@dataclass
class DeveloperRecord:
    name: str
    email: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
