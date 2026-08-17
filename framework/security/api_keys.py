import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class APIKeyRecord:
    key_id: str
    developer_id: str
    project_id: str
    environment: str
    secret_hash: str
    permissions: set[str] = field(default_factory=set)
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None

def generate_api_key() -> tuple[str, str]:
    secret = "adf_" + secrets.token_urlsafe(32)
    return secret, hashlib.sha256(secret.encode()).hexdigest()

def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
