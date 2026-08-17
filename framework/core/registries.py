from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any
from framework.errors import ValidationError

@dataclass(frozen=True, slots=True)
class ExtensionScope:
    kind: str = "global"
    project_id: str | None = None
    environment: str | None = None
    def matches(self, project_id: str | None, environment: str | None) -> bool:
        if self.kind == "global": return True
        if self.kind == "project": return self.project_id == project_id
        if self.kind == "environment": return self.environment == environment
        if self.kind == "project_environment": return self.project_id == project_id and self.environment == environment
        return False

class Registry:
    def __init__(self) -> None: self._items: dict[str, Any] = {}
    def _key(self, item_or_name: Any, version: str | None = None) -> str:
        if isinstance(item_or_name, str):
            name, scope, project_id, environment = item_or_name, "global", None, None
        else:
            name = getattr(item_or_name, "name", None) or getattr(item_or_name, "plugin_id", None)
            scope, project_id, environment = getattr(item_or_name, "scope", "global"), getattr(item_or_name, "project_id", None), getattr(item_or_name, "environment", None)
        qualifier = f"{scope}:{project_id or ''}:{environment or ''}"
        return f"{name}@{version or getattr(item_or_name, 'version', '1.0.0') if not isinstance(item_or_name, str) else version or '1.0.0'}#{qualifier}"
    def validate(self, item: Any) -> None:
        name = getattr(item, "name", None) or getattr(item, "plugin_id", None)
        if not name or not isinstance(name, str): raise ValidationError("Registered item must expose a string name or plugin_id")
        version = getattr(item, "version", "1.0.0")
        if not isinstance(version, str) or not version: raise ValidationError("Registered item version is required")
        scope = getattr(item, "scope", "global")
        if scope not in {"global", "project", "environment", "project_environment"}: raise ValidationError("Invalid extension scope")
        if scope == "project" and not getattr(item, "project_id", None): raise ValidationError("Project-scoped extension requires project_id")
        if scope == "environment" and not getattr(item, "environment", None): raise ValidationError("Environment-scoped extension requires environment")
    def register(self, item: Any, *, override: bool = False) -> None:
        self.validate(item); key = self._key(item)
        if key in self._items and not override: raise ValidationError(f"Item already registered: {key}")
        self._items[key] = item
    def unregister(self, name: str, version: str | None = None, *, project_id: str | None = None) -> None:
        key = self._key(name, version)
        item = self._items.get(key)
        if item is not None and project_id is not None and getattr(item, "project_id", None) != project_id: return
        self._items.pop(key, None)
    def get(self, name: str, version: str | None = None) -> Any | None:
        item = self._items.get(self._key(name, version))
        if item is not None: return item
        candidates = [value for value in self._items.values() if (getattr(value, "name", None) or getattr(value, "plugin_id", None)) == name and (version is None or getattr(value, "version", "1.0.0") == version)]
        return next((value for value in candidates if getattr(value, "scope", "global") == "global"), None)
    def exists(self, name: str, version: str | None = None) -> bool: return self.get(name, version) is not None
    def resolve(self, name: str, *, version: str | None = None, project_id: str | None = None, environment: str | None = None) -> Any | None:
        candidates = [item for item in self._items.values() if (getattr(item, "name", None) or getattr(item, "plugin_id", None)) == name and getattr(item, "scope", "global") in {"global", "project", "environment", "project_environment"} and ExtensionScope(getattr(item, "scope", "global"), getattr(item, "project_id", None), getattr(item, "environment", None)).matches(project_id, environment)]
        if version: candidates = [item for item in candidates if getattr(item, "version", "1.0.0") == version]
        if not candidates: return None
        candidates.sort(key=lambda item: (getattr(item, "scope", "global") == "global", getattr(item, "version", "1.0.0")), reverse=False)
        return candidates[0]
    def list(self, *, project_id: str | None = None, environment: str | None = None) -> list[Any]:
        return [item for item in self._items.values() if ExtensionScope(getattr(item, "scope", "global"), getattr(item, "project_id", None), getattr(item, "environment", None)).matches(project_id, environment)]
    def names(self) -> list[str]: return sorted({getattr(item, "name", None) or getattr(item, "plugin_id", None) for item in self._items.values()})

class ActionRegistry(Registry):
    def validate(self, item: Any) -> None:
        super().validate(item)
        if not callable(getattr(item, "execute", None)) or not inspect.iscoroutinefunction(item.execute): raise ValidationError("Action execute must be async")

class ToolRegistry(Registry):
    def validate(self, item: Any) -> None:
        super().validate(item)
        if not callable(getattr(item, "execute", None)) or not inspect.iscoroutinefunction(item.execute): raise ValidationError("Tool execute must be async")

class ProviderRegistry(Registry):
    def validate(self, item: Any) -> None:
        super().validate(item)
        if not callable(getattr(item, "health", None)): raise ValidationError("Provider must expose health")
    def resolve_provider(self, provider_type: str, *, name: str | None = None, project_id: str | None = None, environment: str | None = None) -> Any | None:
        items = [item for item in self.list(project_id=project_id, environment=environment) if getattr(item, "provider_type", None) == provider_type]
        if name: items = [item for item in items if getattr(item, "name", None) == name]
        return items[0] if items else None

class PolicyRegistry(Registry): pass
class MiddlewareRegistry(Registry): pass
class HookRegistry(Registry): pass
class PluginRegistry(Registry): pass
