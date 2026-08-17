from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class DeveloperORM(Base):
    __tablename__ = "developers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class ProjectORM(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("developers.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    environment: Mapped[str] = mapped_column(String(32), default="development", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class APIKeyORM(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    developer_id: Mapped[str] = mapped_column(ForeignKey("developers.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="default", nullable=False)
    prefix: Mapped[str] = mapped_column(String(64), default="adf_development_", nullable=False)
    key_type: Mapped[str] = mapped_column(String(32), default="development", nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class SessionORM(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dialogue: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class DatasetCatalogORM(Base):
    __tablename__ = "dataset_catalogs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="ar", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), default="1", nullable=False)
    current_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class DatasetORM(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    examples: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    lineage: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="ar", nullable=False)
    statistics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class ModelORM(Base):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    training_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), default="rasa", nullable=False)
    artifact_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evaluation_report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    deployment_environment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deployment_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    runtime_state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class BotORM(Base):
    __tablename__ = "bots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="disabled")
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class WebhookSubscriptionORM(Base):
    __tablename__ = "webhook_subscriptions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    timeout_seconds: Mapped[float] = mapped_column(default=10.0, nullable=False)
    max_retries: Mapped[int] = mapped_column(default=3, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class WebhookDeliveryLogORM(Base):
    __tablename__ = "webhook_delivery_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    webhook_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status_code: Mapped[int | None] = mapped_column(nullable=True)
    attempt: Mapped[int] = mapped_column(nullable=False)
    duration_ms: Mapped[float] = mapped_column(nullable=False, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

class TrainingJobORM(Base):
    __tablename__ = "training_jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    framework_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rasa_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    random_seed: Mapped[int | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class UsageEventORM(Base):
    __tablename__ = "usage_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class AuditLogORM(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

@dataclass
class SQLDatabase:
    url: str
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None

    def connect(self) -> None:
        if self.url.startswith("postgres://"):
            self.url = "postgresql+asyncpg://" + self.url.removeprefix("postgres://")
        if self.url.startswith("postgresql://"):
            self.url = "postgresql+asyncpg://" + self.url.removeprefix("postgresql://")
        self.engine = create_async_engine(self.url, pool_pre_ping=True, pool_recycle=1800)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def ping(self) -> bool:
        if not self.engine: self.connect()
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True

    async def create_schema(self) -> None:
        if not self.engine: self.connect()
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if not self.session_factory: self.connect()
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        if self.engine: await self.engine.dispose()

class SQLProjectRepository:
    def __init__(self, database: SQLDatabase): self.database = database
    async def get(self, project_id: str) -> ProjectORM | None:
        async with self.database.session() as session:
            return (await session.execute(select(ProjectORM).where(ProjectORM.id == project_id))).scalar_one_or_none()
        return None
    async def create(self, project: ProjectORM) -> ProjectORM:
        async with self.database.session() as session:
            session.add(project); await session.commit(); await session.refresh(project); return project
        raise RuntimeError("Database session unavailable")
