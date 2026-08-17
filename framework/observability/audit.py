from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from framework.infrastructure.sql import AuditLogORM, SQLDatabase

@dataclass
class AuditEvent:
    event_name: str
    actor_id: str | None = None
    project_id: str | None = None
    ip: str | None = None
    changes: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class AuditLogger:
    def __init__(self, database: SQLDatabase | None = None): self.database, self.events = database, []
    async def record(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        if self.database:
            async with self.database.session() as session:
                session.add(AuditLogORM(id=event.id, event_name=event.event_name, actor_id=event.actor_id, project_id=event.project_id, payload={"ip": event.ip, "changes": event.changes}, created_at=event.created_at))
                await session.commit()
        return event
