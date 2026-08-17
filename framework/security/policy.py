from dataclasses import dataclass
from time import monotonic
from framework.errors import AuthorizationError

@dataclass(frozen=True)
class Permission:
    name: str
    description: str = ""

class PermissionService:
    def __init__(self): self._grants: dict[str, set[str]] = {}
    def grant(self, subject_id: str, permission: str) -> None: self._grants.setdefault(subject_id, set()).add(permission)
    def revoke(self, subject_id: str, permission: str) -> None: self._grants.setdefault(subject_id, set()).discard(permission)
    def check(self, subject_id: str, required: str) -> bool:
        granted = self._grants.get(subject_id, set())
        return required in granted or "*" in granted
    def require(self, subject_id: str, required: str) -> None:
        if not self.check(subject_id, required): raise AuthorizationError(f"Missing permission: {required}")

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
