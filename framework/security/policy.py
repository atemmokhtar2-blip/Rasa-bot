from dataclasses import dataclass
from time import monotonic
from framework.errors import AuthorizationError
from framework.infrastructure.redis import RedisProvider

@dataclass(frozen=True)
class Permission:
    name: str
    description: str = ""

class PermissionService:
    ROLE_PERMISSIONS = {
        "viewer": {"projects.read", "datasets.read", "training.read", "models.read", "bots.read", "usage.read", "audit.read", "keys.read"},
        "developer": {"projects.read", "projects.write", "datasets.read", "datasets.write", "training.read", "training.write", "models.read", "models.evaluate", "models.deploy", "bots.read", "bots.manage", "usage.read", "audit.read", "keys.read", "keys.write", "messages.write"},
        "admin": {"*"},
    }
    def __init__(self): self._grants: dict[str, set[str]] = {}
    def expand(self, permissions: set[str]) -> set[str]:
        expanded = set(permissions)
        for permission in permissions:
            if permission.startswith("role:"): expanded.update(self.ROLE_PERMISSIONS.get(permission.split(":", 1)[1], set()))
        return expanded
    def grant(self, subject_id: str, permission: str) -> None: self._grants.setdefault(subject_id, set()).add(permission)
    def revoke(self, subject_id: str, permission: str) -> None: self._grants.setdefault(subject_id, set()).discard(permission)
    def check(self, subject_id: str, required: str) -> bool:
        granted = self._grants.get(subject_id, set())
        return required in granted or "*" in granted
    def require(self, subject_id: str, required: str) -> None:
        if not self.check(subject_id, required): raise AuthorizationError(f"Missing permission: {required}")

class RedisRateLimiter:
    def __init__(self, redis: RedisProvider, limit: int = 60, window_seconds: int = 60):
        self.redis, self.limit, self.window_seconds = redis, limit, window_seconds
    async def allow(self, key: str) -> bool:
        count = await self.redis.incr_with_expiry(f"rate:{key}", self.window_seconds)
        return count <= self.limit

class FixedWindowRateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60):
        self.limit, self.window_seconds = limit, window_seconds
        self._windows: dict[str, tuple[float, int]] = {}
    def allow(self, key: str) -> bool:
        now = monotonic(); started, count = self._windows.get(key, (now, 0))
        if now - started >= self.window_seconds: started, count = now, 0
        if count >= self.limit:
            self._windows[key] = (started, count)
            return False
        self._windows[key] = (started, count + 1)
        return True
