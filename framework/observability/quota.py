from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from framework.errors import RateLimitError, NotFoundError

@dataclass(frozen=True)
class Quota:
    monthly_requests: int | None = 100000
    daily_requests: int | None = 10000
    training_jobs: int | None = 100
    bots: int | None = 10
    projects: int | None = 10

class QuotaService:
    def __init__(self, usage, project_loader=None): self.usage, self.project_loader = usage, project_loader

    async def limits_for(self, project_id: str) -> Quota:
        try:
            project = await self.project_loader(project_id) if self.project_loader else None
        except NotFoundError:
            project = None
        configuration = dict(getattr(project, "configuration", {}) or {}) if project else {}
        configured = dict(configuration.get("quotas", {}) or {})
        base = asdict(Quota())
        for key in base:
            if key in configured and configured[key] is not None: base[key] = max(0, int(configured[key]))
        return Quota(**base)

    async def snapshot(self, project_id: str, quota: Quota | None = None) -> dict:
        quota = quota or await self.limits_for(project_id)
        now = datetime.now(timezone.utc)
        totals = await self.usage.totals(project_id)
        daily_since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        monthly_since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        daily = await self.usage.window_totals(project_id, since=daily_since)
        monthly = await self.usage.window_totals(project_id, since=monthly_since)
        requests = totals.get("api_request", totals.get("message", 0))
        return {"project_id": project_id, "usage": totals, "windows": {"daily": daily, "monthly": monthly}, "limits": asdict(quota), "remaining": {"monthly_requests": max(0, (quota.monthly_requests or 0) - monthly.get("api_request", monthly.get("message", 0))) if quota.monthly_requests is not None else None, "daily_requests": max(0, (quota.daily_requests or 0) - daily.get("api_request", daily.get("message", 0))) if quota.daily_requests is not None else None, "training_jobs": max(0, (quota.training_jobs or 0) - totals.get("training_job", 0)) if quota.training_jobs is not None else None, "bots": max(0, (quota.bots or 0) - totals.get("bot", 0)) if quota.bots is not None else None, "projects": quota.projects}, "billing": False}

    async def enforce_request(self, project_id: str) -> None:
        quota = await self.limits_for(project_id)
        now = datetime.now(timezone.utc)
        daily_since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        monthly_since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        daily = await self.usage.window_totals(project_id, since=daily_since)
        monthly = await self.usage.window_totals(project_id, since=monthly_since)
        daily_count = daily.get("api_request", daily.get("message", 0))
        monthly_count = monthly.get("api_request", monthly.get("message", 0))
        if quota.daily_requests is not None and daily_count >= quota.daily_requests: raise RateLimitError("Daily request quota exceeded", details={"metric": "daily_requests", "limit": quota.daily_requests, "used": daily_count, "retry_after": 86400})
        if quota.monthly_requests is not None and monthly_count >= quota.monthly_requests: raise RateLimitError("Monthly request quota exceeded", details={"metric": "monthly_requests", "limit": quota.monthly_requests, "used": monthly_count, "retry_after": 2592000})

    async def enforce(self, project_id: str, metric: str, limit: int | None = None) -> None:
        quota = await self.limits_for(project_id)
        selected = limit if limit is not None else getattr(quota, metric, None)
        if selected is None: return
        totals = await self.usage.totals(project_id)
        current = totals.get(metric, 0)
        if current >= selected: raise RateLimitError("Quota exceeded", details={"metric": metric, "limit": selected, "used": current, "retry_after": 3600})
