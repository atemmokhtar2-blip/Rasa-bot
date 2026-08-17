from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from framework.core.models import Entity, IncomingMessage, IntentPrediction, NLUResult, OutgoingResponse

class ProviderBase(ABC):
    name: str = "provider"
    version: str = "1.0.0"
    provider_type: str = "provider"
    scope: str = "global"
    project_id: str | None = None
    environment: str | None = None
    async def health(self) -> dict[str, Any]: return {"status": "ready", "provider": self.name, "version": self.version, "details": {}}

class NLUProvider(ProviderBase):
    provider_type = "nlu"
    @abstractmethod
    async def parse(self, message: IncomingMessage, context: Any = None) -> NLUResult: ...
    async def train(self, dataset: Any) -> Any: raise NotImplementedError
    async def evaluate(self, model: Any) -> dict[str, Any]: raise NotImplementedError

class ModelProvider(ProviderBase):
    provider_type = "model"
    @abstractmethod
    async def load(self, model: Any) -> Any: ...
    @abstractmethod
    async def unload(self, model: Any) -> None: ...
    @abstractmethod
    async def predict(self, model: Any, payload: Any, context: Any = None) -> Any: ...
    async def metadata(self, model: Any) -> dict[str, Any]: return {}

class StorageProvider(ProviderBase):
    provider_type = "storage"
    @abstractmethod
    async def get(self, key: str) -> Any: ...
    @abstractmethod
    async def set(self, key: str, value: Any) -> None: ...
    @abstractmethod
    async def delete(self, key: str) -> None: ...
    @abstractmethod
    async def list(self, prefix: str = "") -> list[str]: ...

class SessionProvider(ProviderBase):
    provider_type = "session"
    @abstractmethod
    async def get_session(self, session_id: str) -> Any: ...
    @abstractmethod
    async def create_session(self, project_id: str, user_id: str, **metadata: Any) -> Any: ...
    @abstractmethod
    async def update_session(self, session_id: str, **values: Any) -> Any: ...
    @abstractmethod
    async def delete_session(self, session_id: str) -> None: ...

class ChannelProvider(ProviderBase):
    provider_type = "channel"
    channel: str = "custom"
    @abstractmethod
    async def normalize(self, payload: Any, *, project_id: str) -> IncomingMessage: ...
    @abstractmethod
    async def send(self, response: OutgoingResponse, *, recipient_id: str) -> Any: ...

class ExtensionNLUAdapter:
    def __init__(self, provider): self.provider, self.name, self.version = provider, getattr(provider, "name", provider.__class__.__name__), getattr(provider, "version", "1.0.0")
    async def analyze(self, message: IncomingMessage, context: Any = None) -> NLUResult: return await self.provider.parse(message, context)
    async def health(self): return await self.provider.health()

class CoreNLUAdapter(NLUProvider):
    def __init__(self, provider, name: str): self.provider, self.name, self.version = provider, name, getattr(provider, "version", "1.0.0")
    async def parse(self, message: IncomingMessage, context: Any = None) -> NLUResult:
        from framework.core.models import ProcessingContext, RequestContext
        return await self.provider.analyze(message, ProcessingContext(message, RequestContext(project_id=message.project_id), metadata=context or {}))
    async def health(self): return await self.provider.health()

class FakeNLUProvider(NLUProvider):
    name, version = "fake-nlu", "1.0.0"
    async def parse(self, message: IncomingMessage, context: Any = None) -> NLUResult:
        text = (message.text or "").strip().lower()
        intent = text.removeprefix("/").split()[0] if text.startswith("/") and text.removeprefix("/") else "fallback"
        return NLUResult(IntentPrediction(intent, 1.0), [], provider=self.name, model_version=self.version)

class FakeModelProvider(ModelProvider):
    name, version = "fake-model", "1.0.0"
    async def load(self, model: Any) -> Any: return model
    async def unload(self, model: Any) -> None: return None
    async def predict(self, model: Any, payload: Any, context: Any = None) -> dict[str, Any]: return {"model": model, "payload": payload}

class FakeStorageProvider(StorageProvider):
    name, version = "fake-storage", "1.0.0"
    def __init__(self): self.values: dict[str, Any] = {}
    async def get(self, key: str) -> Any: return self.values.get(key)
    async def set(self, key: str, value: Any) -> None: self.values[key] = value
    async def delete(self, key: str) -> None: self.values.pop(key, None)
    async def list(self, prefix: str = "") -> list[str]: return sorted(key for key in self.values if key.startswith(prefix))

class FakeSessionProvider(SessionProvider):
    name, version = "fake-session", "1.0.0"
    def __init__(self): self.values: dict[str, dict[str, Any]] = {}
    async def get_session(self, session_id: str) -> Any: return self.values.get(session_id)
    async def create_session(self, project_id: str, user_id: str, **metadata: Any) -> Any:
        import uuid
        session_id = uuid.uuid4().hex; self.values[session_id] = {"id": session_id, "project_id": project_id, "user_id": user_id, **metadata}; return self.values[session_id]
    async def update_session(self, session_id: str, **values: Any) -> Any: self.values[session_id].update(values); return self.values[session_id]
    async def delete_session(self, session_id: str) -> None: self.values.pop(session_id, None)
