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
    def __init__(self, database: SQLDatabase | None = None):
        self.database = database
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

    async def create_project(self, owner_id: str, name: str, description: str = "", environment: str = "development") -> ProjectRecord:
        if not self.database:
            if await self.developers.get(owner_id) is None: raise NotFoundError("Developer not found")
            return await self.projects.create(ProjectRecord(name=name, owner_id=owner_id, description=description, environment=environment))
        async with self.database.session() as session:
            owner = (await session.execute(select(DeveloperORM).where(DeveloperORM.id == owner_id))).scalar_one_or_none()
            if owner is None: raise NotFoundError("Developer not found")
            record = ProjectORM(id=secrets.token_urlsafe(16), owner_id=owner_id, name=name, description=description, environment=environment, status="active", configuration={})
            session.add(record); await session.commit()
        return ProjectRecord(id=record.id, name=record.name, owner_id=record.owner_id, description=record.description, environment=record.environment, status=record.status, created_at=record.created_at, updated_at=record.updated_at)

    async def create_api_key(self, developer_id: str, project_id: str, environment: str, permissions: set[str]) -> APIKeyCreation:
        secret, digest = generate_api_key(); key_id = "key_" + secrets.token_urlsafe(12)
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
        digest = hash_api_key(secret)
        if not self.database:
            for key in self.api_keys.values():
                if key.secret_hash == digest and key.status == "active": key.last_used_at = datetime.now(timezone.utc); return key
            raise AuthenticationError("Invalid or inactive API key")
        async with self.database.session() as session:
            row = (await session.execute(select(APIKeyORM).where(APIKeyORM.secret_hash == digest, APIKeyORM.status == "active"))).scalar_one_or_none()
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
            secret, digest = generate_api_key(); new_id = "key_" + secrets.token_urlsafe(12)
            self.api_keys[new_id] = APIKeyRecord(new_id, old.developer_id, old.project_id, old.environment, digest, old.permissions)
            return APIKeyCreation(new_id, secret, old.project_id, old.environment)
        async with self.database.session() as session:
            old = await session.get(APIKeyORM, key_id)
            if old is None: raise NotFoundError("API key not found")
            old.status = "rotated"
            secret, digest = generate_api_key(); new_id = "key_" + secrets.token_urlsafe(12)
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
