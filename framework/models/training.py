from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol
from framework.datasets.io import RasaExporter
from framework.datasets.system import DatasetVersion
from framework.training.reproducibility import ReproducibilityManifest

@dataclass(frozen=True)
class TrainingConfiguration:
    language: str = "ar"
    pipeline: list[str] = field(default_factory=list)
    policies: list[str] = field(default_factory=list)
    epochs: int | None = None
    batch_size: int | None = None
    random_seed: int | None = 42
    evaluation: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 3600.0
    max_memory_mb: int | None = None
    def to_dict(self) -> dict[str, Any]: return {"language": self.language, "pipeline": self.pipeline, "policies": self.policies, "epochs": self.epochs, "batch_size": self.batch_size, "random_seed": self.random_seed, "evaluation": self.evaluation, "timeout_seconds": self.timeout_seconds, "max_memory_mb": self.max_memory_mb}

@dataclass
class TrainingJob:
    project_id: str
    dataset_version: str
    provider: str
    status: str = "queued"
    metrics: dict[str, float] = field(default_factory=dict)
    artifact_uri: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    training_config: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    framework_version: str | None = None
    provider_version: str | None = None
    rasa_version: str | None = None
    random_seed: int | None = None

@dataclass
class TrainingResult:
    status: str
    artifact_uri: str | None = None
    logs: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

class TrainingProvider(Protocol):
    async def train(self, dataset_version: DatasetVersion, configuration: TrainingConfiguration) -> TrainingResult: ...

class RasaTrainer:
    def __init__(self, executable: str = "rasa"): self.executable = executable
    async def train(self, project_id: str, dataset_version: str, config_path: str, output_dir: str, timeout_seconds: float = 3600.0) -> TrainingJob:
        job = TrainingJob(project_id, dataset_version, "rasa", status="training")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        try:
            process = await asyncio.create_subprocess_exec(self.executable, "train", "--config", config_path, "--out", output_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            job.status = "failed"; job.error = "RASA_TRAINING_TIMEOUT"; raise RuntimeError(job.error) from exc
        if process.returncode != 0:
            job.status = "failed"; job.error = stderr.decode(errors="replace")[-4000:]; raise RuntimeError(f"Rasa training failed: {job.error}")
        job.status = "ready"; job.artifact_uri = output_dir; job.logs = stdout.decode(errors="replace")[-4000:].splitlines(); return job

class RasaTrainingProvider:
    version = "1.0"
    def __init__(self, executable: str = "rasa", work_root: str = "./data/training", rasa_version: str = "3.x"): self.trainer = RasaTrainer(executable); self.work_root = Path(work_root); self.rasa_version = rasa_version
    async def train_dataset(self, dataset_version: DatasetVersion, configuration: TrainingConfiguration) -> TrainingResult:
        job_root = self.work_root / dataset_version.project_id / dataset_version.version; job_root.mkdir(parents=True, exist_ok=True)
        exported = RasaExporter(self.rasa_version).export(dataset_version)
        for filename, data in exported.items():
            if filename.endswith(".yml"): (job_root / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        config_path = job_root / "config.yml"; config_path.write_text(json.dumps({"language": configuration.language, "pipeline": configuration.pipeline, "policies": configuration.policies, "seed": configuration.random_seed}, ensure_ascii=False, indent=2), encoding="utf-8")
        output_dir = job_root / "models"
        try:
            result = await self.trainer.train(dataset_version.project_id, dataset_version.version, str(config_path), str(output_dir), configuration.timeout_seconds)
            manifest = ReproducibilityManifest.build(dataset_version=dataset_version.version, dataset_checksum=dataset_version.checksum or dataset_version.calculate_checksum(), training_config=configuration.to_dict(), model_version=f"{dataset_version.project_id}:{dataset_version.version}", framework_version="rasa-framework", random_seed=configuration.random_seed, language=configuration.language, hyperparameters={"epochs": configuration.epochs, "batch_size": configuration.batch_size}, evaluation_results={})
            return TrainingResult("completed", result.artifact_uri, result.logs, result.metrics, metadata={"dataset_version": dataset_version.version, "dataset_checksum": dataset_version.checksum or dataset_version.calculate_checksum(), "training_config": configuration.to_dict(), "provider_version": self.version, "rasa_version": self.rasa_version, "reproducibility_manifest": manifest.to_dict()})
        except Exception as exc:
            manifest = ReproducibilityManifest.build(dataset_version=dataset_version.version, dataset_checksum=dataset_version.checksum or dataset_version.calculate_checksum(), training_config=configuration.to_dict(), model_version=f"{dataset_version.project_id}:{dataset_version.version}", framework_version="rasa-framework", random_seed=configuration.random_seed, language=configuration.language, hyperparameters={"epochs": configuration.epochs, "batch_size": configuration.batch_size}, evaluation_results={})
            return TrainingResult("failed", logs=[str(exc)], error_code="RASA_TRAINING_FAILED", error_message="Rasa training failed", metadata={"dataset_version": dataset_version.version, "dataset_checksum": dataset_version.checksum or dataset_version.calculate_checksum(), "training_config": configuration.to_dict(), "provider_version": self.version, "rasa_version": self.rasa_version, "reproducibility_manifest": manifest.to_dict()})
    async def train(self, dataset_version: DatasetVersion, configuration: TrainingConfiguration) -> TrainingResult:
        return await self.train_dataset(dataset_version, configuration)
