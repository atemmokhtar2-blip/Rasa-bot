from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4
from framework.infrastructure.sql import AuditLogORM, SQLDatabase
from sqlalchemy import delete, select
from framework.security.redaction import SensitiveDataRedactor

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
    def __init__(self, database: SQLDatabase | None = None, redactor: SensitiveDataRedactor | None = None): self.database, self.events, self.redactor = database, [], redactor or SensitiveDataRedactor()
    async def purge_older_than(self, retention_days: int) -> int:
        if retention_days < 1: raise ValueError("retention_days must be positive")
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        if not self.database:
            before = len(self.events); self.events = [event for event in self.events if event.created_at >= cutoff]; return before - len(self.events)
        async with self.database.session() as session:
            result = await session.execute(delete(AuditLogORM).where(AuditLogORM.created_at < cutoff))
            await session.commit()
            return int(result.rowcount or 0)

    async def list_project(self, project_id: str, limit: int = 100) -> list[AuditEvent]:
        limit = max(1, min(limit, 1000))
        if not self.database:
            return [event for event in self.events if event.project_id == project_id][-limit:]
        async with self.database.session() as session:
            rows = (await session.execute(select(AuditLogORM).where(AuditLogORM.project_id == project_id).order_by(AuditLogORM.created_at.desc()).limit(limit))).scalars().all()
            return [AuditEvent(event_name=row.event_name, actor_id=row.actor_id, project_id=row.project_id, changes=dict((row.payload or {}).get("changes", {})), id=row.id, created_at=row.created_at) for row in rows]

    async def record(self, event: AuditEvent) -> AuditEvent:
        event.changes = self.redactor.redact(event.changes)
        self.events.append(event)
        if self.database:
            async with self.database.session() as session:
                session.add(AuditLogORM(id=event.id, event_name=event.event_name, actor_id=event.actor_id, project_id=event.project_id, payload={"ip": event.ip, "changes": event.changes}, created_at=event.created_at))
                await session.commit()
        return event
