import hashlib
import hmac
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
    expires_at: datetime | None = None
    name: str | None = None
    prefix: str | None = None
    key_type: str = "development"
    metadata: dict = field(default_factory=dict)

def generate_api_key(pepper: str = "", environment: str = "development") -> tuple[str, str]:
    key_type = environment.lower() if environment.lower() in {"live", "test", "development", "staging"} else "development"
    secret = f"adf_{key_type}_" + secrets.token_urlsafe(32)
    return secret, hash_api_key(secret, pepper)

def hash_api_key(secret: str, pepper: str = "") -> str:
    return hmac.new(pepper.encode(), secret.encode(), hashlib.sha256).hexdigest()
