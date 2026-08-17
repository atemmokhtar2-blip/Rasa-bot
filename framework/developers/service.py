from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
from framework.infrastructure.database import DeveloperRecord, InMemoryRepository, ProjectRecord
from framework.infrastructure.sql import APIKeyORM, DeveloperORM, ProjectORM, SQLDatabase
from framework.security.api_keys import APIKeyRecord, generate_api_key, hash_api_key
from framework.errors import AuthenticationError, NotFoundError
from sqlalchemy import select

@dataclass
class APIKeyCreation:
    key_id: str
    secret: str
    project_id: str
    environment: str

class DeveloperService:
    def __init__(self, database: SQLDatabase | None = None, pepper: str = ""):
        self.database = database
        self.pepper = pepper
        self.developers = InMemoryRepository()
        self.projects = InMemoryRepository()
        self.api_keys: dict[str, APIKeyRecord] = {}

    async def create_developer(self, name: str, email: str) -> DeveloperRecord:
        if not self.database:
            return await self.developers.create(DeveloperRecord(name=name, email=email))
        record = DeveloperORM(id=secrets.token_urlsafe(16), name=name, email=email)
        async with self.database.session() as session:
            session.add(record); await session.commit()
        return DeveloperRecord(id=record.id, name=record.name, email=record.email, created_at=record.created_at)

    @staticmethod
    def _project_record(row: ProjectORM) -> ProjectRecord:
        return ProjectRecord(id=row.id, name=row.name, owner_id=row.owner_id, description=row.description, environment=row.environment, status=row.status, created_at=row.created_at, updated_at=row.updated_at)

    async def list_developers(self) -> list[DeveloperRecord]:
        if not self.database:
            return list(self.developers.items.values())
        async with self.database.session() as session:
            rows = (await session.execute(select(DeveloperORM).order_by(DeveloperORM.created_at))).scalars().all()
            return [DeveloperRecord(id=row.id, name=row.name, email=row.email, created_at=row.created_at) for row in rows]

    async def get_developer(self, developer_id: str) -> DeveloperRecord:
        if not self.database:
            row = await self.developers.get(developer_id)
            if row is None: raise NotFoundError("Developer not found")
            return row
        async with self.database.session() as session:
            row = await session.get(DeveloperORM, developer_id)
            if row is None: raise NotFoundError("Developer not found")
            return DeveloperRecord(id=row.id, name=row.name, email=row.email, created_at=row.created_at)

    async def list_projects(self, owner_id: str | None = None) -> list[ProjectRecord]:
        if not self.database:
            rows = list(self.projects.items.values())
            return [row for row in rows if owner_id is None or row.owner_id == owner_id]
        async with self.database.session() as session:
            statement = select(ProjectORM).order_by(ProjectORM.created_at)
            if owner_id is not None: statement = statement.where(ProjectORM.owner_id == owner_id)
            rows = (await session.execute(statement)).scalars().all()
            return [self._project_record(row) for row in rows]

    async def get_project(self, project_id: str) -> ProjectRecord:
        if not self.database:
            row = await self.projects.get(project_id)
            if row is None: raise NotFoundError("Project not found")
            return row
        async with self.database.session() as session:
            row = await session.get(ProjectORM, project_id)
            if row is None: raise NotFoundError("Project not found")
            return self._project_record(row)

    async def update_project(self, project_id: str, **values) -> ProjectRecord:
        allowed = {"name", "description", "environment", "status"}
        values = {key: value for key, value in values.items() if key in allowed and value is not None}
        if not self.database:
            row = await self.get_project(project_id)
            for key, value in values.items(): setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            return row
        async with self.database.session() as session:
            row = await session.get(ProjectORM, project_id)
            if row is None: raise NotFoundError("Project not found")
            for key, value in values.items(): setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            await session.commit(); await session.refresh(row)
            return self._project_record(row)

    async def create_project(self, owner_id: str, name: str, description: str = "", environment: str = "development") -> ProjectRecord:
        if not self.database:
            if await self.developers.get(owner_id) is None: raise NotFoundError("Developer not found")
            return await self.projects.create(ProjectRecord(name=name, owner_id=owner_id, description=description, environment=environment))
        async with self.database.session() as session:
            owner = (await session.execute(select(DeveloperORM).where(DeveloperORM.id == owner_id))).scalar_one_or_none()
            if owner is None: raise NotFoundError("Developer not found")
            record = ProjectORM(id=secrets.token_urlsafe(16), owner_id=owner_id, name=name, description=description, environment=environment, status="active", configuration={})
            session.add(record); await session.commit()
        return self._project_record(record)

    async def create_api_key(self, developer_id: str, project_id: str, environment: str, permissions: set[str]) -> APIKeyCreation:
        secret, digest = generate_api_key(self.pepper); key_id = "key_" + secrets.token_urlsafe(12)
        if not self.database:
            project = await self.projects.get(project_id)
            if project is None or project.owner_id != developer_id: raise NotFoundError("Project not found for developer")
            self.api_keys[key_id] = APIKeyRecord(key_id=key_id, developer_id=developer_id, project_id=project_id, environment=environment, secret_hash=digest, permissions=permissions)
            return APIKeyCreation(key_id, secret, project_id, environment)
        async with self.database.session() as session:
            project = (await session.execute(select(ProjectORM).where(ProjectORM.id == project_id, ProjectORM.owner_id == developer_id))).scalar_one_or_none()
            if project is None: raise NotFoundError("Project not found for developer")
            session.add(APIKeyORM(id=key_id, developer_id=developer_id, project_id=project_id, environment=environment, secret_hash=digest, permissions=sorted(permissions), status="active")); await session.commit()
        return APIKeyCreation(key_id, secret, project_id, environment)

    async def authenticate(self, secret: str) -> APIKeyRecord:
        digest = hash_api_key(secret, self.pepper)
        if not self.database:
            now = datetime.now(timezone.utc)
            for key in self.api_keys.values():
                if key.secret_hash == digest and key.status == "active" and (key.expires_at is None or key.expires_at > now): key.last_used_at = now; return key
            raise AuthenticationError("Invalid or inactive API key")
        async with self.database.session() as session:
            now = datetime.now(timezone.utc)
            row = (await session.execute(select(APIKeyORM).where(APIKeyORM.secret_hash == digest, APIKeyORM.status == "active", (APIKeyORM.expires_at.is_(None) | (APIKeyORM.expires_at > now))))).scalar_one_or_none()
            if row is None: raise AuthenticationError("Invalid or inactive API key")
            row.last_used_at = datetime.now(timezone.utc); await session.commit()
            return APIKeyRecord(key_id=row.id, developer_id=row.developer_id, project_id=row.project_id, environment=row.environment, secret_hash=row.secret_hash, permissions=set(row.permissions), status=row.status, created_at=row.created_at, last_used_at=row.last_used_at)
        raise AuthenticationError("Invalid or inactive API key")

    async def revoke_api_key(self, key_id: str) -> None:
        if not self.database:
            key = self.api_keys.get(key_id)
            if key is None: raise NotFoundError("API key not found")
            key.status = "revoked"; return
        async with self.database.session() as session:
            row = await session.get(APIKeyORM, key_id)
            if row is None: raise NotFoundError("API key not found")
            row.status = "revoked"; await session.commit()

    async def get_api_key(self, key_id: str) -> APIKeyRecord:
        if not self.database:
            row = self.api_keys.get(key_id)
            if row is None: raise NotFoundError("API key not found")
            return row
        async with self.database.session() as session:
            row = await session.get(APIKeyORM, key_id)
            if row is None: raise NotFoundError("API key not found")
            return APIKeyRecord(key_id=row.id, developer_id=row.developer_id, project_id=row.project_id, environment=row.environment, secret_hash="[redacted]", permissions=set(row.permissions), status=row.status, created_at=row.created_at, last_used_at=row.last_used_at)

    async def list_api_keys(self, project_id: str) -> list[APIKeyRecord]:
        if not self.database:
            return [key for key in self.api_keys.values() if key.project_id == project_id]
        result: list[APIKeyRecord] = []
        async with self.database.session() as session:
            rows = (await session.execute(select(APIKeyORM).where(APIKeyORM.project_id == project_id))).scalars().all()
            for row in rows:
                result.append(APIKeyRecord(key_id=row.id, developer_id=row.developer_id, project_id=row.project_id, environment=row.environment, secret_hash="[redacted]", permissions=set(row.permissions), status=row.status, created_at=row.created_at, last_used_at=row.last_used_at))
        return result

    async def rotate_api_key(self, key_id: str) -> APIKeyCreation:
        if not self.database:
            old = self.api_keys.get(key_id)
            if old is None: raise NotFoundError("API key not found")
            old.status = "rotated"
            secret, digest = generate_api_key(self.pepper); new_id = "key_" + secrets.token_urlsafe(12)
            self.api_keys[new_id] = APIKeyRecord(new_id, old.developer_id, old.project_id, old.environment, digest, old.permissions)
            return APIKeyCreation(new_id, secret, old.project_id, old.environment)
        async with self.database.session() as session:
            old = await session.get(APIKeyORM, key_id)
            if old is None: raise NotFoundError("API key not found")
            old.status = "rotated"
            secret, digest = generate_api_key(self.pepper); new_id = "key_" + secrets.token_urlsafe(12)
            session.add(APIKeyORM(id=new_id, developer_id=old.developer_id, project_id=old.project_id, environment=old.environment, secret_hash=digest, permissions=old.permissions, status="active")); await session.commit()
            return APIKeyCreation(new_id, secret, old.project_id, old.environment)
        raise NotFoundError("API key not found")

    async def disable_api_key(self, key_id: str) -> None:
        await self._set_key_status(key_id, "disabled")

    async def expire_api_key(self, key_id: str) -> None:
        await self._set_key_status(key_id, "expired")

    async def _set_key_status(self, key_id: str, status: str) -> None:
        if not self.database:
            key = self.api_keys.get(key_id)
            if key is None: raise NotFoundError("API key not found")
            key.status = status; return
        async with self.database.session() as session:
            key = await session.get(APIKeyORM, key_id)
            if key is None: raise NotFoundError("API key not found")
            key.status = status; await session.commit()
