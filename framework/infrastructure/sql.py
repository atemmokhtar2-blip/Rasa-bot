from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, select
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
    secret_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
