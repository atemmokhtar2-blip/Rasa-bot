from dataclasses import dataclass
from datetime import datetime, timezone
from framework.infrastructure.domain_repositories import ModelRepository

@dataclass
class DeploymentResult:
    model_id: str
    status: str
    previous_model_id: str | None
    deployed_at: datetime

class ModelDeploymentService:
    def __init__(self, repository: ModelRepository): self.repository, self.active = repository, {}
    async def _active_model(self, project_id: str) -> str | None:
        if hasattr(self.repository, "list_project"):
            rows = await self.repository.list_project(project_id)
            deployed = next((row for row in rows if row.status == "deployed"), None)
            return deployed.id if deployed else self.active.get(project_id)
        return self.active.get(project_id)
    async def deploy(self, project_id: str, model_id: str, canary: bool = False) -> DeploymentResult:
        previous = await self._active_model(project_id)
        await self.repository.set_status(model_id, "canary" if canary else "deployed")
        if not canary:
            if previous and previous != model_id: await self.repository.set_status(previous, "ready")
            self.active[project_id] = model_id
        return DeploymentResult(model_id, "canary" if canary else "deployed", previous, datetime.now(timezone.utc))
    async def promote_canary(self, project_id: str, model_id: str, healthy: bool, reason: str = "") -> DeploymentResult:
        rows = await self.repository.list_project(project_id)
        model = next((row for row in rows if row.id == model_id), None)
        if model is None: raise ValueError(f"Model {model_id} does not belong to project {project_id}")
        metrics = dict(model.metrics or {})
        metrics["health"] = {"healthy": healthy, "reason": reason}
        await self.repository.update_metrics(model_id, metrics)
        if not healthy:
            await self.repository.set_status(model_id, "failed")
            return DeploymentResult(model_id, "failed", await self._active_model(project_id), datetime.now(timezone.utc))
        return await self.deploy(project_id, model_id, canary=False)

    async def rollback(self, project_id: str) -> DeploymentResult:
        previous = await self._active_model(project_id)
        if previous is None: raise ValueError(f"No active model for project {project_id}")
        await self.repository.set_status(previous, "rolled_back")
        self.active.pop(project_id, None)
        return DeploymentResult(previous, "rolled_back", None, datetime.now(timezone.utc))
