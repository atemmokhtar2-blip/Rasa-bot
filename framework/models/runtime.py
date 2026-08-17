from __future__ import annotations
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
import httpx
from framework.errors import FrameworkError

@dataclass(frozen=True)
class RuntimeDiscovery:
    model_id: str
    version: str
    artifact_uri: str
    artifact_checksum: str | None
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class RuntimeHandle:
    discovery: RuntimeDiscovery
    state: str = "discovered"
    loaded_at: str | None = None
    last_used_at: str | None = None
    requests: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    adapter_handle: Any = None
    def to_dict(self) -> dict[str, Any]: return {"model_id": self.discovery.model_id, "version": self.discovery.version, "provider": self.discovery.provider, "artifact_uri": self.discovery.artifact_uri, "state": self.state, "loaded_at": self.loaded_at, "last_used_at": self.last_used_at, "requests": self.requests, "metadata": self.metadata}

class ModelRuntimeAdapter(Protocol):
    async def load(self, discovery: RuntimeDiscovery) -> Any: ...
    async def validate(self, handle: Any, discovery: RuntimeDiscovery) -> dict[str, Any]: ...
    async def serve(self, handle: Any, text: str, metadata: dict[str, Any]) -> dict[str, Any]: ...
    async def unload(self, handle: Any) -> None: ...

class RasaHTTPRuntimeAdapter:
    def __init__(self, endpoint: str, timeout: float = 10.0): self.endpoint, self.timeout = endpoint.rstrip("/"), timeout
    async def load(self, discovery: RuntimeDiscovery) -> dict[str, Any]: return {"endpoint": self.endpoint, "model_id": discovery.model_id, "version": discovery.version}
    async def validate(self, handle: dict[str, Any], discovery: RuntimeDiscovery) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.endpoint}/status"); response.raise_for_status()
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {"status": "ready", "provider": discovery.provider, "remote_model_version": data.get("version"), "endpoint": self.endpoint}
    async def serve(self, handle: dict[str, Any], text: str, metadata: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.endpoint}/model/parse", json={"text": text, "metadata": metadata}); response.raise_for_status(); data = response.json()
        if not isinstance(data, dict): raise FrameworkError("Model runtime returned a non-object response")
        return data
    async def unload(self, handle: dict[str, Any]) -> None: return None

class ModelRuntimeCache:
    def __init__(self, max_entries: int = 2, ttl_seconds: float = 3600.0):
        if max_entries < 1 or ttl_seconds <= 0: raise ValueError("invalid runtime cache configuration")
        self.max_entries, self.ttl_seconds = max_entries, ttl_seconds; self._items: OrderedDict[str, RuntimeHandle] = OrderedDict()
    def get(self, key: str) -> RuntimeHandle | None:
        item = self._items.get(key)
        if item is None: return None
        if item.last_used_at and time.time() - datetime.fromisoformat(item.last_used_at).timestamp() > self.ttl_seconds:
            self._items.pop(key, None); return None
        self._items.move_to_end(key); return item
    def expired(self) -> list[RuntimeHandle]:
        now = time.time(); expired = [item for item in self._items.values() if item.last_used_at and now - datetime.fromisoformat(item.last_used_at).timestamp() > self.ttl_seconds]
        for item in expired: self._items.pop(item.discovery.model_id, None)
        return expired
    def put(self, key: str, value: RuntimeHandle) -> list[RuntimeHandle]:
        evicted: list[RuntimeHandle] = []; self._items[key] = value; self._items.move_to_end(key)
        while len(self._items) > self.max_entries: _, item = self._items.popitem(last=False); evicted.append(item)
        return evicted
    def remove(self, key: str) -> RuntimeHandle | None: return self._items.pop(key, None)
    def keys(self) -> list[str]: return list(self._items)

class ModelRuntimeService:
    def __init__(self, model_repository=None, *, adapter: ModelRuntimeAdapter | None = None, cache: ModelRuntimeCache | None = None, rasa_endpoint: str | None = None, router: Any = None):
        self.model_repository, self.adapter, self.router = model_repository, adapter or (RasaHTTPRuntimeAdapter(rasa_endpoint) if rasa_endpoint else None), router; self.cache = cache or ModelRuntimeCache(); self._locks: dict[str, Any] = {}
    async def resolve_and_serve(self, project_id: str, text: str, *, environment: str = "production", alias: str = "production", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.router is None: raise FrameworkError("Model router is not configured")
        target = self.router.resolve(project_id, environment, alias)
        if target is None: raise FrameworkError("No model is configured for project/environment/alias")
        model_id, version = target
        if self.model_repository is None: raise FrameworkError("Model repository is required for routed runtime")
        model = await self.model_repository.get(model_id)
        if model is None or model.project_id != project_id or model.version != version: raise FrameworkError("Resolved model is unavailable")
        return await self.serve(model, text, metadata)
    async def discover(self, model) -> RuntimeDiscovery:
        if not model.artifact_uri: raise FrameworkError("Model artifact is required for runtime discovery")
        artifact_uri = str(model.artifact_uri); metadata = {"project_id": model.project_id}
        if not artifact_uri.startswith(("http://", "https://", "s3://")):
            path = Path(artifact_uri)
            if not path.exists(): raise FrameworkError("Model artifact does not exist")
            if path.is_file() and model.artifact_checksum:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != model.artifact_checksum: raise FrameworkError("Model artifact checksum mismatch")
            metadata["artifact_exists"] = True
        return RuntimeDiscovery(model.id, model.version, artifact_uri, model.artifact_checksum, model.provider, metadata)
    async def _persist(self, model_id: str, handle: RuntimeHandle) -> None:
        if self.model_repository: await self.model_repository.update_fields(model_id, runtime_state=handle.to_dict())
    async def load(self, model) -> RuntimeHandle:
        if self.adapter is None: raise FrameworkError("RASA_ENDPOINT is required for model runtime")
        discovery = await self.discover(model); key = discovery.model_id
        for expired in self.cache.expired():
            await self.adapter.unload(expired.adapter_handle); expired.state = "unloaded"; await self._persist(expired.discovery.model_id, expired)
        cached = self.cache.get(key)
        if cached and cached.discovery.version == discovery.version and cached.state == "ready": return cached
        if cached:
            self.cache.remove(key); await self.adapter.unload(cached.adapter_handle); cached.state = "unloaded"; await self._persist(cached.discovery.model_id, cached)
        handle = RuntimeHandle(discovery); handle.state = "loading"; handle.adapter_handle = await self.adapter.load(discovery)
        validation = await self.adapter.validate(handle.adapter_handle, discovery)
        if validation.get("status") != "ready": handle.state = "failed"; handle.metadata = validation; await self._persist(model.id, handle); raise FrameworkError("Model runtime validation failed")
        handle.state, handle.loaded_at, handle.last_used_at, handle.metadata = "ready", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), validation
        for evicted in self.cache.put(key, handle):
            await self.adapter.unload(evicted.adapter_handle); evicted.state = "unloaded"; await self._persist(evicted.discovery.model_id, evicted)
        await self._persist(model.id, handle); return handle
    async def serve(self, model, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        handle = await self.load(model)
        result = await self.adapter.serve(handle.adapter_handle, text, metadata or {})
        handle.requests += 1; handle.last_used_at = datetime.now(timezone.utc).isoformat(); self.cache.put(handle.discovery.model_id, handle); await self._persist(model.id, handle)
        return result
    async def unload(self, model_id: str) -> dict[str, Any]:
        handle = self.cache.remove(model_id)
        if handle is None: return {"model_id": model_id, "state": "unloaded", "cached": False}
        if self.adapter: await self.adapter.unload(handle.adapter_handle)
        handle.state = "unloaded"; await self._persist(model_id, handle); return handle.to_dict()
    async def status(self, model_id: str) -> dict[str, Any]:
        handle = self.cache.get(model_id); return handle.to_dict() if handle else {"model_id": model_id, "state": "not_loaded", "cached": False}
    async def close(self) -> None:
        for key in list(self.cache.keys()): await self.unload(key)

__all__ = ["RuntimeDiscovery", "RuntimeHandle", "ModelRuntimeAdapter", "RasaHTTPRuntimeAdapter", "ModelRuntimeCache", "ModelRuntimeService"]
