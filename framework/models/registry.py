from __future__ import annotations
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

class ModelStatus:
    CREATED = "created"; EVALUATING = "evaluating"; READY = "ready"; DEPLOYED = "deployed"; DISABLED = "disabled"; FAILED = "failed"; ARCHIVED = "archived"; ROLLED_BACK = "rolled_back"

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
    project_id: str | None = None
    training_job_id: str | None = None
    artifact_checksum: str | None = None
    evaluation_report: dict[str, Any] = field(default_factory=dict)
    quality_gate: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

class ModelProviderRegistry:
    def __init__(self): self._providers: dict[str, Any] = {}
    def register(self, name: str, provider: Any) -> None:
        if name in self._providers: raise ValueError(f"Model provider already registered: {name}")
        self._providers[name] = provider
    def get(self, name: str) -> Any | None: return self._providers.get(name)
    def names(self) -> list[str]: return sorted(self._providers)

class ModelRegistry:
    VALID_STATUSES = {"training", "created", "evaluating", "ready", "deployed", "disabled", "failed", "archived", "rolled_back"}
    def __init__(self): self._models: dict[tuple[str, str], ModelVersion] = {}; self._active: dict[tuple[str, str], tuple[str, str]] = {}; self._history: dict[tuple[str, str], list[tuple[str, str]]] = {}; self._aliases: dict[tuple[str, str, str], tuple[str, str]] = {}
    def register(self, model: ModelVersion) -> ModelVersion:
        if model.status not in self.VALID_STATUSES: raise ValueError("Invalid model status")
        key = (model.model_id, model.version)
        if key in self._models: raise ValueError("Model version already exists")
        self._models[key] = model; return model
    def register_version(self, model: ModelVersion, *, lineage: dict[str, Any] | None = None) -> ModelVersion:
        model.metadata = {**model.metadata, "lineage": lineage or {}, "immutable": True}
        return self.register(model)
    def get(self, model_id: str, version: str | None = None) -> ModelVersion | None:
        if version is not None: return self._models.get((model_id, version))
        candidates = [model for (mid, _), model in self._models.items() if mid == model_id]
        return sorted(candidates, key=lambda item: item.created_at)[-1] if candidates else None
    def list_project(self, project_id: str) -> list[ModelVersion]: return [model for model in self._models.values() if model.project_id == project_id]
    def mark_ready(self, model_id: str, version: str, evaluation: dict[str, Any], *, artifact_uri: str | None = None, gate_passed: bool = True, failures: list[str] | None = None) -> ModelVersion:
        model = self.get(model_id, version)
        if model is None: raise ValueError("Model not found")
        if not gate_passed: model.status = "failed"; model.quality_gate = {"passed": False, "failures": failures or []}; raise ValueError("Model quality gate rejected model")
        if not artifact_uri and not model.artifact_uri: raise ValueError("Model artifact is required")
        model.status = "ready"; model.evaluation_report = dict(evaluation); model.quality_gate = {"passed": True, "failures": []}; return model
    def set_alias(self, project_id: str, environment: str, alias: str, model_id: str, version: str) -> None:
        model = self.get(model_id, version)
        if model is None or model.project_id != project_id or model.status not in {"ready", "deployed"}: raise ValueError("Model is not available for alias")
        self._aliases[(project_id, environment, alias)] = (model_id, version)
    def resolve_alias(self, project_id: str, environment: str = "production", alias: str = "production") -> ModelVersion | None:
        target = self._aliases.get((project_id, environment, alias)); return self.get(*target) if target else None
    def search(self, project_id: str, *, status: str | None = None, environment: str | None = None, tags: set[str] | None = None) -> list[ModelVersion]:
        rows = self.list_project(project_id)
        if status: rows = [row for row in rows if row.status == status]
        if environment: rows = [row for row in rows if row.metadata.get("environment") == environment or row.metadata.get("deployment_environment") == environment]
        if tags: rows = [row for row in rows if tags.intersection(set(row.metadata.get("tags", [])))]
        return rows
    def deploy(self, project_id: str, model_id: str, version: str, environment: str = "production") -> ModelVersion:
        model = self.get(model_id, version)
        if model is None or model.status not in {"ready", "deployed"}: raise ValueError("Model is not ready for deployment")
        if model.project_id and model.project_id != project_id: raise ValueError("Model does not belong to project")
        key = (project_id, environment); previous_target = self._active.get(key)
        if previous_target and previous_target != (model_id, version):
            previous = self.get(*previous_target)
            if previous: previous.status = "disabled"
        model.status = "deployed"; model.metadata = {**model.metadata, "environment": environment, "tags": sorted(set(model.metadata.get("tags", [])) | {environment})}; self._active[key] = (model_id, version); self._history.setdefault(key, []).append((model_id, version)); self._aliases[(project_id, environment, environment)] = (model_id, version); return model
    def active(self, project_id: str, environment: str = "production") -> str | None:
        target = self._active.get((project_id, environment)); return target[1] if target else None
    def rollback(self, project_id: str, environment: str = "production") -> ModelVersion:
        key = (project_id, environment); history = self._history.get(key, [])
        if len(history) < 2: raise ValueError("No previous model available for rollback")
        current_target = history.pop(); previous_target = history[-1]; current = self.get(*current_target); previous = self.get(*previous_target)
        if current: current.status = "rolled_back"
        if previous is None or previous.project_id != project_id: raise ValueError("Previous model not found")
        previous.status = "deployed"; self._active[key] = previous_target; self._aliases[(project_id, environment, environment)] = previous_target; return previous
    def archive(self, model_id: str, version: str) -> ModelVersion:
        model = self.get(model_id, version)
        if model is None: raise ValueError("Model not found")
        model.status = "archived"; return model
