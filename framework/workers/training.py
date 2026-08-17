from framework.infrastructure.queue import RedisQueue
from framework.infrastructure.domain_repositories import TrainingJobRepository, ModelRepository
from framework.infrastructure.sql import ModelORM
from uuid import uuid4
from framework.models.training import RasaTrainer
from framework.models.artifacts import ModelArtifactService

class TrainingJobWorker:
    def __init__(self, queue: RedisQueue, repository: TrainingJobRepository, trainer: RasaTrainer, model_repository: ModelRepository | None = None, artifact_service: ModelArtifactService | None = None): self.queue, self.repository, self.trainer, self.model_repository, self.artifact_service, self.running = queue, repository, trainer, model_repository, artifact_service, False
    async def run_once(self) -> bool:
        envelope = await self.queue.consume("training", timeout=1)
        if not envelope: return False
        payload = envelope["payload"]
        job_id = payload["job_id"]
        await self.repository.update(job_id, status="training")
        try:
            result = await self.trainer.train(payload["project_id"], payload["dataset_version"], payload["config_path"], payload["output_dir"])
            artifact_uri = result.artifact_uri
            metrics = dict(result.metrics)
            if self.artifact_service and result.artifact_uri:
                artifact_uri, digest = await self.artifact_service.publish_directory(payload["project_id"], job_id, result.artifact_uri)
                metrics["artifact_sha256"] = digest
            await self.repository.update(job_id, status=result.status, artifact_uri=artifact_uri, metrics=metrics, error=result.error)
            if self.model_repository and artifact_uri:
                await self.model_repository.save(ModelORM(id=uuid4().hex, project_id=payload['project_id'], version=payload['dataset_version'], dataset_id=payload['dataset_version'], artifact_uri=artifact_uri, status='ready', metrics=metrics))
        except Exception as exc:
            await self.repository.update(job_id, status="failed", error=str(exc))
        return True

    async def run(self) -> None:
        self.running = True
        while self.running:
            await self.run_once()

    def stop(self) -> None: self.running = False
