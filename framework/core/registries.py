from __future__ import annotations
from typing import Any
from framework.errors import ValidationError

class Registry:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}
    def register(self, item: Any) -> None:
        name = getattr(item, "name", None) or getattr(item, "plugin_id", None)
        if not name:
            raise ValidationError("Registered item must expose name or plugin_id")
        if name in self._items:
            raise ValidationError(f"Item already registered: {name}")
        self._items[name] = item
    def unregister(self, name: str) -> None:
        self._items.pop(name, None)
    def resolve(self, name: str) -> Any | None:
        return self._items.get(name)
    def list(self) -> list[Any]:
        return list(self._items.values())
    def names(self) -> list[str]:
        return sorted(self._items)

class ActionRegistry(Registry): pass
class ToolRegistry(Registry): pass
class PluginRegistry(Registry): pass
