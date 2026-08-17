from __future__ import annotations
import inspect
from typing import Any
from framework.errors import ValidationError

class Registry:
    def __init__(self) -> None: self._items: dict[str, Any] = {}
    def validate(self, item: Any) -> None:
        name = getattr(item, "name", None) or getattr(item, "plugin_id", None)
        if not name or not isinstance(name, str): raise ValidationError("Registered item must expose a string name or plugin_id")
    def register(self, item: Any) -> None:
        self.validate(item); name = getattr(item, "name", None) or getattr(item, "plugin_id", None)
        if name in self._items: raise ValidationError(f"Item already registered: {name}")
        self._items[name] = item
    def unregister(self, name: str) -> None: self._items.pop(name, None)
    def get(self, name: str) -> Any | None: return self._items.get(name)
    def exists(self, name: str) -> bool: return name in self._items
    def resolve(self, name: str) -> Any | None: return self.get(name)
    def list(self) -> list[Any]: return list(self._items.values())
    def names(self) -> list[str]: return sorted(self._items)

class ActionRegistry(Registry):
    def validate(self, item: Any) -> None:
        super().validate(item)
        if not callable(getattr(item, "execute", None)): raise ValidationError("Action must expose execute")
        if not inspect.iscoroutinefunction(item.execute): raise ValidationError("Action execute must be async")

class ToolRegistry(Registry):
    def validate(self, item: Any) -> None:
        super().validate(item)
        if not callable(getattr(item, "execute", None)): raise ValidationError("Tool must expose execute")
        if not inspect.iscoroutinefunction(item.execute): raise ValidationError("Tool execute must be async")

class PluginRegistry(Registry): pass
