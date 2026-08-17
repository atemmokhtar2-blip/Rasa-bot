from dataclasses import dataclass, field
from datetime import datetime, timezone
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
