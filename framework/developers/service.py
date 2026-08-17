from dataclasses import dataclass
from datetime import datetime, timezone
from framework.infrastructure.database import DeveloperRecord, InMemoryRepository, ProjectRecord
from framework.security.api_keys import APIKeyRecord, generate_api_key, hash_api_key
from framework.errors import AuthenticationError, NotFoundError

@dataclass
class APIKeyCreation:
    key_id: str
    secret: str
    project_id: str
    environment: str

class DeveloperService:
    def __init__(self):
        self.developers = InMemoryRepository()
        self.projects = InMemoryRepository()
        self.api_keys: dict[str, APIKeyRecord] = {}

    async def create_developer(self, name: str, email: str) -> DeveloperRecord:
        return await self.developers.create(DeveloperRecord(name=name, email=email))

    async def create_project(self, owner_id: str, name: str, description: str = "", environment: str = "development") -> ProjectRecord:
        if await self.developers.get(owner_id) is None:
            raise NotFoundError("Developer not found")
        return await self.projects.create(ProjectRecord(name=name, owner_id=owner_id, description=description, environment=environment))

    async def create_api_key(self, developer_id: str, project_id: str, environment: str, permissions: set[str]) -> APIKeyCreation:
        project = await self.projects.get(project_id)
        if project is None or project.owner_id != developer_id:
            raise NotFoundError("Project not found for developer")
        import secrets
        secret, digest = generate_api_key()
        key_id = "key_" + secrets.token_urlsafe(12)
        self.api_keys[key_id] = APIKeyRecord(key_id=key_id, developer_id=developer_id, project_id=project_id, environment=environment, secret_hash=digest, permissions=permissions)
        return APIKeyCreation(key_id, secret, project_id, environment)

    async def authenticate(self, secret: str) -> APIKeyRecord:
        digest = hash_api_key(secret)
        for key in self.api_keys.values():
            if key.secret_hash == digest and key.status == "active":
                key.last_used_at = datetime.now(timezone.utc)
                return key
        raise AuthenticationError("Invalid or inactive API key")

    async def revoke_api_key(self, key_id: str) -> None:
        key = self.api_keys.get(key_id)
        if key is None:
            raise NotFoundError("API key not found")
        key.status = "revoked"
