from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from framework.infrastructure.sql import BotORM, DatasetCatalogORM, DatasetORM, ModelORM, SQLDatabase, TrainingJobORM, WebhookSubscriptionORM, WebhookDeliveryLogORM
from framework.datasets.system import DatasetVersion, TrainingExample

class DatasetCatalogRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: DatasetCatalogORM) -> DatasetCatalogORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, dataset_id: str) -> DatasetCatalogORM | None:
        async with self.db.session() as session: return await session.get(DatasetCatalogORM, dataset_id)
    async def list_project(self, project_id: str) -> list[DatasetCatalogORM]:
        async with self.db.session() as session: return list((await session.execute(select(DatasetCatalogORM).where(DatasetCatalogORM.project_id == project_id))).scalars().all())
    async def update(self, dataset_id: str, **values) -> DatasetCatalogORM:
        async with self.db.session() as session:
            row = await session.get(DatasetCatalogORM, dataset_id)
            if row is None: raise KeyError(dataset_id)
            for key, value in values.items(): setattr(row, key, value)
            await session.commit(); await session.refresh(row); return row

class DatabaseDatasetLoader:
    def __init__(self, repository): self.repository = repository
    async def __call__(self, project_id: str, version: str | None = None) -> DatasetVersion:
        row = await self.repository.get(version or project_id)
        if row is None and version is not None: row = await self.repository.get_by_project_version(project_id, version)
        if row is None: raise KeyError(f"Dataset version not found: {project_id}/{version}")
        examples = tuple(TrainingExample(text=item.get("text", ""), intent=item.get("intent", ""), entities=tuple(item.get("entities", [])), metadata=dict(item.get("metadata", {})), language=item.get("language", row.language), source=item.get("source", "manual"), example_id=item.get("example_id", item.get("id")) or uuid4().hex, raw_text=item.get("raw_text"), normalized_text=item.get("normalized_text"), conversation_id=item.get("conversation_id"), difficulty=item.get("difficulty", "medium")) for item in row.examples)
        return DatasetVersion(row.id, row.version, row.project_id, examples, row.schema_version, row.status, statistics=row.statistics or {}, checksum=row.checksum, metadata=row.metadata_json or {})

class DatasetRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: DatasetORM) -> DatasetORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, dataset_id: str) -> DatasetORM | None:
        async with self.db.session() as session: return await session.get(DatasetORM, dataset_id)
    async def list_project(self, project_id: str) -> list[DatasetORM]:
        async with self.db.session() as session: return list((await session.execute(select(DatasetORM).where(DatasetORM.project_id == project_id))).scalars().all())
    async def get_by_project_version(self, project_id: str, version: str) -> DatasetORM | None:
        async with self.db.session() as session: return (await session.execute(select(DatasetORM).where(DatasetORM.project_id == project_id, DatasetORM.version == version))).scalars().first()

class ModelRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: ModelORM) -> ModelORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, model_id: str) -> ModelORM | None:
        async with self.db.session() as session: return await session.get(ModelORM, model_id)
    async def list_project(self, project_id: str) -> list[ModelORM]:
        async with self.db.session() as session: return list((await session.execute(select(ModelORM).where(ModelORM.project_id == project_id))).scalars().all())
    async def update_metrics(self, model_id: str, metrics: dict) -> ModelORM:
        async with self.db.session() as session:
            row = await session.get(ModelORM, model_id)
            if row is None: raise KeyError(model_id)
            row.metrics = metrics; await session.commit(); await session.refresh(row); return row
    async def set_status(self, model_id: str, status: str) -> ModelORM:
        async with self.db.session() as session:
            row = await session.get(ModelORM, model_id)
            if row is None: raise KeyError(model_id)
            row.status = status; await session.commit(); await session.refresh(row); return row
    async def update_fields(self, model_id: str, **values) -> ModelORM:
        async with self.db.session() as session:
            row = await session.get(ModelORM, model_id)
            if row is None: raise KeyError(model_id)
            for key, value in values.items(): setattr(row, key, value)
            await session.commit(); await session.refresh(row); return row

class TrainingJobRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: TrainingJobORM) -> TrainingJobORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, job_id: str) -> TrainingJobORM | None:
        async with self.db.session() as session: return await session.get(TrainingJobORM, job_id)
    async def list_project(self, project_id: str) -> list[TrainingJobORM]:
        async with self.db.session() as session: return list((await session.execute(select(TrainingJobORM).where(TrainingJobORM.project_id == project_id))).scalars().all())
    async def list_running(self) -> list[TrainingJobORM]:
        async with self.db.session() as session: return list((await session.execute(select(TrainingJobORM).where(TrainingJobORM.status.in_(["validating", "preparing", "running", "training", "evaluating"])))).scalars().all())
    async def find_idempotency(self, key: str) -> TrainingJobORM | None:
        async with self.db.session() as session: return (await session.execute(select(TrainingJobORM).where(TrainingJobORM.idempotency_key == key))).scalars().first()
    async def request_cancel(self, job_id: str) -> TrainingJobORM:
        async with self.db.session() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None: raise KeyError(job_id)
            if row.status in {"ready", "failed", "cancelled"}: return row
            row.cancel_requested = True
            if row.status == "queued": row.status = "cancelled"
            await session.commit(); await session.refresh(row); return row
    async def update(self, job_id: str, **values) -> TrainingJobORM:
        async with self.db.session() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None: raise KeyError(job_id)
            for key, value in values.items(): setattr(row, key, value)
            await session.commit(); await session.refresh(row); return row

class WebhookRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: WebhookSubscriptionORM) -> WebhookSubscriptionORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def list_project(self, project_id: str) -> list[WebhookSubscriptionORM]:
        async with self.db.session() as session: return list((await session.execute(select(WebhookSubscriptionORM).where(WebhookSubscriptionORM.project_id == project_id))).scalars().all())
    async def list_all(self) -> list[WebhookSubscriptionORM]:
        async with self.db.session() as session: return list((await session.execute(select(WebhookSubscriptionORM))).scalars().all())
    async def delete_project_webhook(self, project_id: str, webhook_id: str) -> int:
        async with self.db.session() as session:
            row = await session.get(WebhookSubscriptionORM, webhook_id)
            if row is None or row.project_id != project_id: return 0
            await session.delete(row); await session.commit(); return 1
    async def delete_row(self, row_id: str, project_id: str) -> int:
        return await self.delete_project_webhook(project_id, row_id)

class WebhookDeliveryLogRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: WebhookDeliveryLogORM) -> WebhookDeliveryLogORM:
        async with self.db.session() as session:
            session.add(row); await session.commit(); await session.refresh(row); return row
    async def list_project(self, project_id: str, limit: int = 100) -> list[WebhookDeliveryLogORM]:
        async with self.db.session() as session:
            result = await session.execute(select(WebhookDeliveryLogORM).where(WebhookDeliveryLogORM.project_id == project_id).order_by(WebhookDeliveryLogORM.created_at.desc()).limit(max(1, min(limit, 1000))))
            return list(result.scalars().all())

class BotRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: BotORM) -> BotORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, bot_id: str) -> BotORM | None:
        async with self.db.session() as session: return await session.get(BotORM, bot_id)
    async def list_project(self, project_id: str) -> list[BotORM]:
        async with self.db.session() as session: return list((await session.execute(select(BotORM).where(BotORM.project_id == project_id))).scalars().all())
    async def set_status(self, bot_id: str, status: str) -> BotORM:
        async with self.db.session() as session:
            row = await session.get(BotORM, bot_id)
            if row is None: raise KeyError(bot_id)
            row.status = status; await session.commit(); await session.refresh(row); return row
