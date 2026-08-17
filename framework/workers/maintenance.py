import asyncio
from framework.observability.audit import AuditLogger

class MaintenanceWorker:
    def __init__(self, audit: AuditLogger, retention_days: int, interval_seconds: int = 3600):
        self.audit, self.retention_days, self.interval_seconds, self.running = audit, retention_days, interval_seconds, False

    async def run_once(self) -> int:
        return await self.audit.purge_older_than(self.retention_days)

    async def run(self) -> None:
        self.running = True
        while self.running:
            await self.run_once()
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self.running = False
