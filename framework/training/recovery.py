from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any

class TrainingRecoveryService:
    def __init__(self, repository: Any, stale_after_seconds: float = 300.0): self.repository, self.stale_after_seconds = repository, stale_after_seconds
    async def recover_orphaned(self, *, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc); recovered = []
        rows = await self.repository.list_running()
        for row in rows:
            heartbeat = getattr(row, "heartbeat_at", None) or getattr(row, "started_at", None)
            if heartbeat is None or (now - heartbeat).total_seconds() <= self.stale_after_seconds: continue
            retry_count, max_retries = int(getattr(row, "retry_count", 0)), int(getattr(row, "max_retries", 3))
            next_status = "retryable" if retry_count < max_retries else "failed"
            await self.repository.update(row.id, status=next_status, error_code="WORKER_ORPHANED", error="Training worker heartbeat expired", retry_count=retry_count + 1, completed_at=now if next_status == "failed" else None)
            recovered.append(row.id)
        return recovered
