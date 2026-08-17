from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

@dataclass
class ModelVersion:
    model_id: str
    version: str
    provider: str
    dataset_version: str
    status: str = "training"
    metrics: dict[str, float] = field(default_factory=dict)
    artifact_uri: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class ModelRegistry:
    VALID_STATUSES = {"training", "evaluating", "ready", "deployed", "disabled", "failed"}
    def __init__(self): self._models: dict[tuple[str, str], ModelVersion] = {}; self._active: dict[str, str] = {}
    def register(self, model: ModelVersion) -> ModelVersion:
        if model.status not in self.VALID_STATUSES: raise ValueError("Invalid model status")
        key = (model.model_id, model.version)
        if key in self._models: raise ValueError("Model version already exists")
        self._models[key] = model
        return model
    def get(self, model_id: str, version: str) -> ModelVersion | None: return self._models.get((model_id, version))
    def deploy(self, project_id: str, model_id: str, version: str) -> ModelVersion:
        model = self.get(model_id, version)
        if model is None or model.status not in {"ready", "deployed"}: raise ValueError("Model is not ready for deployment")
        previous_version = self._active.get(project_id)
        if previous_version:
            old = self.get(model_id, previous_version)
            if old: old.status = "disabled"
        model.status = "deployed"
        self._active[project_id] = version
        return model
    def active(self, project_id: str) -> str | None: return self._active.get(project_id)
