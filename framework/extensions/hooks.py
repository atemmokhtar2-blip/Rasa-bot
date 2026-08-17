from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

HOOK_NAMES = {"before_request", "after_request", "before_message", "after_message", "before_action", "after_action", "before_tool", "after_tool", "before_model_load", "after_model_load"}
@dataclass(frozen=True, slots=True)
class HookSpec:
    name: str
    handler: Callable[..., Any]
    priority: int = 100
    critical: bool = False
    plugin_id: str | None = None

class HookManager:
    def __init__(self): self._hooks: dict[str, list[HookSpec]] = {name: [] for name in HOOK_NAMES}
    def register(self, name: str, handler: Callable[..., Any], *, priority: int = 100, critical: bool = False, plugin_id: str | None = None) -> None:
        if name not in HOOK_NAMES: raise ValueError(f"Unknown lifecycle hook: {name}")
        self._hooks[name].append(HookSpec(name, handler, priority, critical, plugin_id)); self._hooks[name].sort(key=lambda item: item.priority)
    def unregister_plugin(self, plugin_id: str) -> None:
        for name in self._hooks: self._hooks[name] = [item for item in self._hooks[name] if item.plugin_id != plugin_id]
    async def run(self, name: str, context: Any, **kwargs: Any) -> Any:
        value = context
        for spec in tuple(self._hooks.get(name, [])):
            try:
                result = spec.handler(value, **kwargs)
                value = await result if inspect.isawaitable(result) else result
            except Exception:
                if spec.critical: raise
        return value

@dataclass(frozen=True, slots=True)
class PolicyDefinition:
    name: str
    handler: Callable[..., Any]
    version: str = "1.0.0"
    permissions: frozenset[str] = frozenset()
    scope: str = "global"
    project_id: str | None = None
    environment: str | None = None
    metadata: dict[str, Any] | None = None

class Policy:
    def __init__(self, name: str, handler: Callable[..., Any], *, version: str = "1.0.0", permissions: set[str] | None = None, scope: str = "global", project_id: str | None = None, environment: str | None = None, metadata: dict[str, Any] | None = None): self.definition = PolicyDefinition(name, handler, version, frozenset(permissions or set()), scope, project_id, environment, metadata or {})
    @property
    def name(self): return self.definition.name
    @property
    def version(self): return self.definition.version
    async def evaluate(self, context: Any, **kwargs: Any) -> Any:
        result = self.definition.handler(context, **kwargs); return await result if inspect.isawaitable(result) else result
