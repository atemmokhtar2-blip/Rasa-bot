from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Response:
    data: Any
    success: bool = True
    request_id: str | None = None
    error: dict[str, Any] | None = None
    @property
    def id(self): return self.data.get("id") if isinstance(self.data, dict) else None

@dataclass(frozen=True)
class MessageResponse(Response):
    @property
    def text(self) -> str | None: return ((self.data.get("response") or {}).get("text") if isinstance(self.data, dict) else None)
    @property
    def intent(self) -> dict[str, Any] | None: return self.data.get("intent") if isinstance(self.data, dict) else None
    @property
    def session_id(self) -> str | None: return self.data.get("session_id") if isinstance(self.data, dict) else None
