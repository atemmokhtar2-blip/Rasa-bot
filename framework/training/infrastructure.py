from __future__ import annotations
import asyncio, hashlib, json, shutil, tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

class TrainingBackend(Protocol):
    name: str
    version: str
    async def train(self, dataset: Any, configuration: dict[str, Any], *, job: "TrainingJobContext") -> "BackendResult": ...

@dataclass
class TrainingJobContext:
    job_id: str
    project_id: str
    request_id: str | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    progress: float = 0.0
    current_stage: str = "queued"
    logs: list[str] = field(default_factory=list)
    def heartbeat(self, stage: str, progress: float) -> None:
        self.current_stage, self.progress, self.heartbeat_at = stage, max(0.0, min(1.0, progress)), datetime.now(timezone.utc)
    def log(self, message: str) -> None: self.logs.append(message[-4000:])

@dataclass
class BackendResult:
    status: str
    artifact_uri: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

class ArtifactStore(Protocol):
    async def put_directory(self, project_id: str, artifact_id: str, source: str | Path) -> tuple[str, str]: ...
    async def exists(self, uri: str) -> bool: ...
    async def checksum(self, uri: str) -> str: ...
    async def delete_temporary(self, uri: str) -> None: ...

class LocalArtifactStore:
    def __init__(self, root: str | Path = "./data/artifacts"): self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
    async def put_directory(self, project_id: str, artifact_id: str, source: str | Path) -> tuple[str, str]:
        source = Path(source); target = self.root / project_id / artifact_id; target.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(source, target, dirs_exist_ok=True); return str(target), await self.checksum(str(target))
    async def exists(self, uri: str) -> bool: return Path(uri).exists()
    async def checksum(self, uri: str) -> str:
        path = Path(uri); digest = hashlib.sha256()
        files = sorted(path.rglob("*") if path.is_dir() else [path])
        for item in files:
            if item.is_file(): digest.update(str(item.relative_to(path)).encode()); digest.update(item.read_bytes())
        return digest.hexdigest()
    async def delete_temporary(self, uri: str) -> None:
        path = Path(uri)
        if path.exists(): shutil.rmtree(path) if path.is_dir() else path.unlink()

@dataclass
class TrainingQueueItem:
    job_id: str
    project_id: str
    payload: dict[str, Any]
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class TrainingQueue:
    def __init__(self): self._queue: asyncio.Queue[TrainingQueueItem] = asyncio.Queue(); self._ids: set[str] = set()
    async def enqueue(self, item: TrainingQueueItem) -> bool:
        if item.job_id in self._ids: return False
        self._ids.add(item.job_id); await self._queue.put(item); return True
    async def dequeue(self) -> TrainingQueueItem: return await self._queue.get()
    def task_done(self) -> None: self._queue.task_done()
    def size(self) -> int: return self._queue.qsize()

@dataclass
class QualityGateDecision:
    passed: bool
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

class ConfigurableQualityGate:
    def __init__(self, thresholds: dict[str, float] | None = None): self.thresholds = dict(thresholds or {})
    def evaluate(self, metrics: dict[str, float]) -> QualityGateDecision:
        failures = [f"{key}<{threshold}" for key, threshold in self.thresholds.items() if metrics.get(key) is None or metrics[key] < threshold]
        return QualityGateDecision(not failures, failures, dict(metrics))

@dataclass
class ModelLineage:
    model_id: str
    model_version: str
    training_job_id: str
    dataset_id: str
    dataset_version: str
    data_sources: list[str] = field(default_factory=list)
    training_config: dict[str, Any] = field(default_factory=dict)
    framework_version: str | None = None
    backend_version: str | None = None

class ModelRouter:
    def __init__(self): self._aliases: dict[tuple[str, str, str], tuple[str, str]] = {}
    def set_alias(self, project_id: str, environment: str, alias: str, model_id: str, version: str) -> None: self._aliases[(project_id, environment, alias)] = (model_id, version)
    def resolve(self, project_id: str, environment: str = "production", alias: str = "production") -> tuple[str, str] | None: return self._aliases.get((project_id, environment, alias))
    def remove(self, project_id: str, environment: str, alias: str = "production") -> None: self._aliases.pop((project_id, environment, alias), None)

class DeploymentManager:
    def __init__(self, router: ModelRouter, artifact_store: ArtifactStore): self.router, self.artifact_store, self.history = router, artifact_store, {}
    async def deploy(self, project_id: str, model_id: str, version: str, artifact_uri: str, *, environment: str = "production", alias: str = "production") -> dict[str, Any]:
        if not await self.artifact_store.exists(artifact_uri): raise ValueError("Model artifact does not exist")
        previous = self.router.resolve(project_id, environment, alias); self.router.set_alias(project_id, environment, alias, model_id, version)
        record = {"deployment_id": uuid4().hex, "project_id": project_id, "model_id": model_id, "version": version, "artifact_uri": artifact_uri, "environment": environment, "alias": alias, "previous": previous, "created_at": datetime.now(timezone.utc).isoformat()}; self.history.setdefault((project_id, environment, alias), []).append(record); return record
    async def rollback(self, project_id: str, *, environment: str = "production", alias: str = "production") -> dict[str, Any]:
        history = self.history.get((project_id, environment, alias), []); current = self.router.resolve(project_id, environment, alias)
        if len(history) < 2: raise ValueError("No previous deployment")
        previous = history[-1].get("previous")
        if not previous: raise ValueError("Previous deployment is unavailable")
        artifact = history[-2]
        if not await self.artifact_store.exists(artifact["artifact_uri"] if "artifact_uri" in artifact else ""): raise ValueError("Previous artifact is unavailable")
        self.router.set_alias(project_id, environment, alias, previous[0], previous[1]); return {"rolled_back_from": current, "rolled_back_to": previous}
