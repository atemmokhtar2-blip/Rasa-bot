from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4
from sqlalchemy import select
from framework.infrastructure.sql import SQLDatabase, UsageEventORM

@dataclass
class UsageEvent:
    project_id: str
    metric: str
    quantity: int = 1
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class UsageMeter:
    def __init__(self, database: SQLDatabase | None = None): self.database, self.events = database, []
    async def record(self, event: UsageEvent) -> UsageEvent:
        self.events.append(event)
        if self.database:
            async with self.database.session() as session:
                session.add(UsageEventORM(id=event.id, project_id=event.project_id, metric=event.metric, quantity=event.quantity, request_id=event.request_id, metadata_json=event.metadata, created_at=event.created_at))
                await session.commit()
        return event
    async def list_events(self, project_id: str, limit: int = 100) -> list[UsageEvent]:
        limit = max(1, min(limit, 1000))
        if not self.database:
            return [event for event in self.events if event.project_id == project_id][-limit:]
        async with self.database.session() as session:
            rows = (await session.execute(select(UsageEventORM).where(UsageEventORM.project_id == project_id).order_by(UsageEventORM.created_at.desc()).limit(limit))).scalars().all()
            return [UsageEvent(project_id=row.project_id, metric=row.metric, quantity=row.quantity, request_id=row.request_id, metadata=dict(row.metadata_json or {}), id=row.id, created_at=row.created_at) for row in rows]

    async def window_totals(self, project_id: str, *, since: datetime) -> dict[str, int]:
        if not self.database:
            totals: dict[str, int] = {}
            for event in self.events:
                if event.project_id == project_id and event.created_at >= since: totals[event.metric] = totals.get(event.metric, 0) + event.quantity
            return totals
        totals: dict[str, int] = {}
        async with self.database.session() as session:
            rows = (await session.execute(select(UsageEventORM).where(UsageEventORM.project_id == project_id, UsageEventORM.created_at >= since))).scalars().all()
            for event in rows: totals[event.metric] = totals.get(event.metric, 0) + event.quantity
        return totals

    async def totals(self, project_id: str) -> dict[str, int]:
        if not self.database:
            totals: dict[str, int] = {}
            for event in self.events:
                if event.project_id == project_id: totals[event.metric] = totals.get(event.metric, 0) + event.quantity
            return totals
        totals: dict[str, int] = {}
        async with self.database.session() as session:
            rows = (await session.execute(select(UsageEventORM).where(UsageEventORM.project_id == project_id))).scalars().all()
            for event in rows: totals[event.metric] = totals.get(event.metric, 0) + event.quantity
        return totals
