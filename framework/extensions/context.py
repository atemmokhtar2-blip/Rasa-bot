from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
import httpx
from framework.errors import AuthorizationError

class ScopedConfig:
    def __init__(self, values: dict[str, Any] | None = None, schema: dict[str, Any] | None = None): self._values, self._schema = dict(values or {}), dict(schema or {})
    def get(self, key: str, default: Any = None) -> Any: return self._values.get(key, default)
    def set(self, key: str, value: Any) -> None:
        if self._schema and key not in self._schema: raise ValueError(f"Unknown plugin configuration key: {key}")
        self._values[key] = value
    def validate(self) -> None:
        for key in self._schema.get("required", []):
            if key not in self._values: raise ValueError(f"Missing plugin configuration key: {key}")

class SecretFacade:
    def __init__(self, provider: Any, permissions: set[str]): self._provider, self._permissions = provider, permissions
    def get(self, name: str) -> str | None:
        if "secrets.read" not in self._permissions and "*" not in self._permissions: raise AuthorizationError("Plugin lacks secrets.read permission")
        value = self._provider.get(name)
        return value

class ScopedStorage:
    def __init__(self, backend: Any, project_id: str, permissions: set[str]): self._backend, self.project_id, self._permissions = backend, project_id, permissions
    async def get(self, key: str) -> Any:
        if "storage.read" not in self._permissions and "*" not in self._permissions: raise AuthorizationError("Plugin lacks storage.read permission")
        return await self._backend.get(f"project:{self.project_id}:{key}")
    async def set(self, key: str, value: Any) -> None:
        if "storage.write" not in self._permissions and "*" not in self._permissions: raise AuthorizationError("Plugin lacks storage.write permission")
        await self._backend.set(f"project:{self.project_id}:{key}", value)
    async def delete(self, key: str) -> None:
        if "storage.write" not in self._permissions and "*" not in self._permissions: raise AuthorizationError("Plugin lacks storage.write permission")
        await self._backend.delete(f"project:{self.project_id}:{key}")
    async def list(self, prefix: str = "") -> list[str]:
        if "storage.read" not in self._permissions and "*" not in self._permissions: raise AuthorizationError("Plugin lacks storage.read permission")
        return await self._backend.list(f"project:{self.project_id}:{prefix}")

class ResourceRegistry:
    def __init__(self): self._resources: dict[str, Any] = {}
    def register(self, resource_id: str, resource: Any) -> Any:
        if resource_id in self._resources: raise ValueError(f"Resource already registered: {resource_id}")
        self._resources[resource_id] = resource; return resource
    def unregister(self, resource_id: str) -> None: self._resources.pop(resource_id, None)
    def active(self) -> dict[str, Any]: return {key: value for key, value in self._resources.items() if not getattr(value, "closed", False) and not getattr(value, "done", lambda: False)()}
    def count(self) -> int: return len(self.active())
    async def close_all(self) -> None:
        failures = []
        for resource_id, resource in list(self._resources.items()):
            try:
                close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
                if close:
                    result = close()
                    if asyncio.iscoroutine(result): await result
                self._resources.pop(resource_id, None)
            except Exception as exc: failures.append((resource_id, exc))
        if failures: raise RuntimeError(f"Failed to close resources: {[item[0] for item in failures]}")

class NetworkFacade:
    def __init__(self, permissions: set[str], resources: ResourceRegistry, timeout: float = 10.0): self._permissions, self._resources, self._timeout = permissions, resources, timeout
    def _require(self):
        if "network.outbound" not in self._permissions and "*" not in self._permissions: raise AuthorizationError("Plugin lacks network.outbound permission")
    async def request(self, method: str, url: str, **kwargs):
        self._require(); resource_id = f"http:{id(kwargs)}:{id(self)}"; client = self._resources.register(resource_id, httpx.AsyncClient(timeout=self._timeout))
        try: return await client.request(method, url, **kwargs)
        finally: await client.aclose(); self._resources.unregister(resource_id)
    async def get(self, url: str, **kwargs): return await self.request("GET", url, **kwargs)
    async def post(self, url: str, **kwargs): return await self.request("POST", url, **kwargs)

class TaskManager:
    def __init__(self): self._tasks: set[asyncio.Task] = set()
    def create(self, awaitable: Awaitable[Any]) -> asyncio.Task:
        task = asyncio.create_task(awaitable); self._tasks.add(task); task.add_done_callback(self._tasks.discard); return task
    async def cancel_all(self) -> None:
        tasks = list(self._tasks)
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
    @property
    def active_count(self) -> int: return sum(not task.done() for task in self._tasks)

class ScopedEvents:
    def __init__(self, event_bus: Any, project_id: str, permissions: set[str]): self._bus, self.project_id, self._permissions = event_bus, project_id, permissions; self._subscriptions=[]
    def subscribe(self, event_name: str, handler: Callable[..., Any]) -> None:
        if "events.subscribe" not in self._permissions and "*" not in self._permissions: raise AuthorizationError("Plugin lacks events.subscribe permission")
        async def scoped(event):
            if event.project_id in {None, self.project_id}: return await handler(event) if asyncio.iscoroutinefunction(handler) else handler(event)
        self._bus.subscribe(event_name, scoped); self._subscriptions.append((event_name, scoped))
    def unsubscribe_all(self) -> None:
        for event_name, handler in self._subscriptions: self._bus.unsubscribe(event_name, handler)
        self._subscriptions.clear()

@dataclass(slots=True)
class ExtensionContext:
    plugin_id: str
    project_id: str | None
    environment: str
    permissions: set[str]
    logger: Any
    config: ScopedConfig
    events: ScopedEvents
    tasks: TaskManager
    storage: ScopedStorage | None = None
    secrets: SecretFacade | None = None
    registry: Any = None
    runtime: Any = None
    project: Any = None
    request_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    resources: ResourceRegistry = field(default_factory=ResourceRegistry)
    network: NetworkFacade | None = None
    def require(self, permission: str) -> None:
        if permission not in self.permissions and "*" not in self.permissions: raise AuthorizationError(f"Plugin lacks permission: {permission}")
