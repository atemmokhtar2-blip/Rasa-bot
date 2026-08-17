from datetime import datetime, timezone
from sqlalchemy import select
from framework.infrastructure.sql import BotORM, DatasetORM, ModelORM, SQLDatabase, TrainingJobORM

class DatasetRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: DatasetORM) -> DatasetORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, dataset_id: str) -> DatasetORM | None:
        async with self.db.session() as session: return await session.get(DatasetORM, dataset_id)
    async def list_project(self, project_id: str) -> list[DatasetORM]:
        async with self.db.session() as session: return list((await session.execute(select(DatasetORM).where(DatasetORM.project_id == project_id))).scalars().all())

class ModelRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: ModelORM) -> ModelORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, model_id: str) -> ModelORM | None:
        async with self.db.session() as session: return await session.get(ModelORM, model_id)
    async def list_project(self, project_id: str) -> list[ModelORM]:
        async with self.db.session() as session: return list((await session.execute(select(ModelORM).where(ModelORM.project_id == project_id))).scalars().all())
    async def set_status(self, model_id: str, status: str) -> ModelORM:
        async with self.db.session() as session:
            row = await session.get(ModelORM, model_id)
            if row is None: raise KeyError(model_id)
            row.status = status; await session.commit(); await session.refresh(row); return row

class TrainingJobRepository:
    def __init__(self, db: SQLDatabase): self.db = db
    async def save(self, row: TrainingJobORM) -> TrainingJobORM:
        async with self.db.session() as session: session.add(row); await session.commit(); await session.refresh(row); return row
    async def get(self, job_id: str) -> TrainingJobORM | None:
        async with self.db.session() as session: return await session.get(TrainingJobORM, job_id)
    async def list_project(self, project_id: str) -> list[TrainingJobORM]:
        async with self.db.session() as session: return list((await session.execute(select(TrainingJobORM).where(TrainingJobORM.project_id == project_id))).scalars().all())
    async def update(self, job_id: str, **values) -> TrainingJobORM:
        async with self.db.session() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None: raise KeyError(job_id)
            for key, value in values.items(): setattr(row, key, value)
            await session.commit(); await session.refresh(row); return row

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
