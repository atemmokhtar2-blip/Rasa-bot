from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from framework.infrastructure.queue import RedisQueue
from framework.infrastructure.domain_repositories import TrainingJobRepository, ModelRepository
from framework.infrastructure.sql import ModelORM
from framework.models.training import RasaTrainer, RasaTrainingProvider, TrainingConfiguration
from framework.models.artifacts import ModelArtifactService
from framework.datasets.pipeline import DatasetPipeline
from framework.models.evaluation import EvaluationEngine, QualityGate
from framework.core.models import Entity, IntentPrediction
from framework.models.error_analysis import ErrorAnalyzer, RetrainingPlanner

class TrainingJobWorker:
    def __init__(self, queue: RedisQueue, repository: TrainingJobRepository, trainer: RasaTrainer, model_repository: ModelRepository | None = None, artifact_service: ModelArtifactService | None = None, dataset_loader=None, dataset_pipeline: DatasetPipeline | None = None, evaluation_engine: EvaluationEngine | None = None, quality_gate: QualityGate | None = None, worker_id: str | None = None, heartbeat_interval: float = 5.0):
        self.queue, self.repository, self.trainer, self.model_repository, self.artifact_service = queue, repository, trainer, model_repository, artifact_service; self.dataset_loader = dataset_loader; self.dataset_pipeline = dataset_pipeline or DatasetPipeline(); self.evaluation_engine = evaluation_engine or EvaluationEngine(); self.quality_gate = quality_gate or QualityGate(); self.error_analyzer = ErrorAnalyzer(); self.retraining_planner = RetrainingPlanner(); self.running = False; self.worker_id = worker_id or f"training-worker-{uuid4().hex[:12]}"; self.heartbeat_interval = heartbeat_interval
    async def _heartbeat(self, job_id: str, stage: str, progress: float, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.repository.update(job_id, worker_id=self.worker_id, heartbeat_at=datetime.now(timezone.utc), current_stage=stage, progress=progress)
            try: await asyncio.wait_for(stop.wait(), timeout=self.heartbeat_interval)
            except asyncio.TimeoutError: pass
    async def run_once(self) -> bool:
        envelope = await self.queue.consume("training", timeout=1)
        if not envelope: return False
        payload = envelope["payload"]; job_id = payload["job_id"]; current = await self.repository.get(job_id)
        if current is None: return True
        if current.cancel_requested or current.status == "cancelled": await self.repository.update(job_id, status="cancelled", error="Cancellation requested before execution"); return True
        await self.repository.update(job_id, status="validating", started_at=datetime.now(timezone.utc), worker_id=self.worker_id, heartbeat_at=datetime.now(timezone.utc), current_stage="validating", progress=0.05)
        heartbeat_stop = asyncio.Event(); heartbeat_task = asyncio.create_task(self._heartbeat(job_id, "validating", 0.05, heartbeat_stop))
        try:
            result = None; dataset = None
            if self.dataset_loader and isinstance(self.trainer, RasaTrainingProvider):
                await self.repository.update(job_id, status="preparing", current_stage="preparing", progress=0.15, heartbeat_at=datetime.now(timezone.utc))
                dataset = await self.dataset_loader(payload["dataset_version"])
                known_intents = set(payload.get("known_intents", [])); known_entities = set(payload.get("known_entities", [])); prepared, report = self.dataset_pipeline.prepare(dataset, known_intents, known_entities)
                if report.errors: raise ValueError("Dataset validation failed")
                await self.repository.update(job_id, status="running", current_stage="training", progress=0.30, heartbeat_at=datetime.now(timezone.utc))
                configuration = TrainingConfiguration(**payload.get("training_config", {})); result = await self.trainer.train_dataset(prepared, configuration)
            else:
                await self.repository.update(job_id, status="training")
                result = await self.trainer.train(payload["project_id"], payload["dataset_version"], payload["config_path"], payload["output_dir"], payload.get("timeout_seconds", 3600.0))
            await self.repository.update(job_id, status="evaluating", current_stage="evaluating", progress=0.75, heartbeat_at=datetime.now(timezone.utc))
            artifact_uri = result.artifact_uri; metrics = dict(result.metrics); error = getattr(result, "error", None) or getattr(result, "error_message", None)
            if self.artifact_service and artifact_uri:
                artifact_uri, digest = await self.artifact_service.publish_directory(payload["project_id"], job_id, artifact_uri); metrics["artifact_sha256"] = digest
            status = "completed" if getattr(result, "status", "") in {"completed", "ready"} else getattr(result, "status", "failed")
            await self.repository.update(job_id, status=status, artifact_uri=artifact_uri, metrics=metrics, error=error, logs=getattr(result, "logs", []), configuration=payload.get("training_config", {}), provider_version=getattr(result, "metadata", {}).get("provider_version"), rasa_version=getattr(result, "metadata", {}).get("rasa_version"), completed_at=datetime.now(timezone.utc))
            if self.model_repository and artifact_uri and status == "completed":
                model = await self.model_repository.save(ModelORM(id=job_id, project_id=payload["project_id"], version=payload["dataset_version"], dataset_id=payload["dataset_version"], dataset_version=payload["dataset_version"], training_job_id=job_id, provider=payload.get("provider", "rasa"), artifact_uri=artifact_uri, status="evaluating", metrics=metrics, artifact_checksum=metrics.get("artifact_sha256")))
                raw_samples = payload.get("evaluation_samples") or getattr(result, "metadata", {}).get("evaluation_samples", [])
                if not raw_samples:
                    await self.model_repository.update_fields(model.id, status="failed", evaluation_report={"quality_gate": {"passed": False, "failures": ["evaluation_data_missing"]}})
                else:
                    samples = []
                    for sample in raw_samples:
                        prediction_data = sample.get("prediction") or {"name": sample.get("predicted_intent", "fallback"), "confidence": sample.get("confidence", 0.0)}
                        prediction = prediction_data if isinstance(prediction_data, IntentPrediction) else IntentPrediction(prediction_data.get("name", prediction_data.get("intent", "fallback")), float(prediction_data.get("confidence", 0.0)))
                        entities = [item if isinstance(item, Entity) else Entity(item.get("name", ""), item.get("value"), float(item.get("confidence", 1.0))) for item in sample.get("entities", [])]
                        samples.append({"prediction": prediction, "expected_intent": sample.get("expected_intent", "fallback"), "expected_entities": sample.get("expected_entities", {}), "entities": entities, "action_success": sample.get("action_success", False)})
                    evaluation = self.evaluation_engine.evaluate(model.id, model.version, samples)
                    error_analysis = self.error_analyzer.analyze(samples)
                    retraining_plan = self.retraining_planner.plan(model_version=model.version, dataset_version=payload["dataset_version"], report=error_analysis)
                    gate_values = {key: value for key, value in (payload.get("quality_gate") or {}).items() if key in {"min_intent_f1", "min_entity_f1", "max_fallback_rate", "require_artifact"}}
                    gate = QualityGate(**gate_values) if gate_values else self.quality_gate
                    passed, failures = gate.check(evaluation, artifact_uri, training_succeeded=True)
                    report = {"evaluation": evaluation.to_dict(), "error_analysis": error_analysis.to_dict(), "retraining_plan": retraining_plan.to_dict() if retraining_plan else None, "quality_gate": {"passed": passed, "failures": failures}}
                    await self.model_repository.update_fields(model.id, status="ready" if passed else "failed", metrics={**metrics, "evaluation": evaluation.to_dict()}, evaluation_report=report)
        except asyncio.CancelledError:
            await self.repository.update(job_id, status="cancelled", error="Worker task cancelled", current_stage="cancelled", progress=1.0, completed_at=datetime.now(timezone.utc)); raise
        except Exception as exc:
            await self.repository.update(job_id, status="failed", error=str(exc), error_code="TRAINING_WORKER_FAILED", current_stage="failed", progress=1.0, completed_at=datetime.now(timezone.utc))
        finally:
            heartbeat_stop.set(); heartbeat_task.cancel(); await asyncio.gather(heartbeat_task, return_exceptions=True)
        return True
    async def run(self) -> None:
        self.running = True
        while self.running: await self.run_once()
    def stop(self) -> None: self.running = False
