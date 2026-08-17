from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
from framework.core.models import Entity
from framework.errors import ValidationError

@dataclass(frozen=True)
class IntentDefinition:
    id: str
    name: str
    description: str = ""
    project_id: str | None = None
    version: str = "1.0.0"
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class EntityDefinition:
    name: str
    normalizer: Callable[[Any], Any] | None = None
    validator: Callable[[Any], bool] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    def normalize(self, value: Any) -> Any: return self.normalizer(value) if self.normalizer else value
    def validate(self, value: Any) -> bool: return self.validator(value) if self.validator else True

class IntentRegistry:
    def __init__(self): self._items: dict[str, IntentDefinition] = {}
    def validate(self, intent: IntentDefinition) -> None:
        if not intent.name or not intent.id: raise ValidationError("Intent id and name are required")
    def register(self, intent: IntentDefinition) -> None: self.validate(intent); self._items[intent.name] = intent
    def unregister(self, name: str) -> None: self._items.pop(name, None)
    def get(self, name: str) -> IntentDefinition | None: return self._items.get(name)
    def resolve(self, name: str) -> IntentDefinition | None: return self.get(name)
    def exists(self, name: str) -> bool: return name in self._items
    def list(self) -> list[IntentDefinition]: return list(self._items.values())
    def names(self) -> list[str]: return sorted(self._items)

class EntityRegistry:
    def __init__(self): self._items: dict[str, EntityDefinition] = {}
    def validate(self, entity: EntityDefinition) -> None:
        if not entity.name: raise ValidationError("Entity name is required")
    def register(self, entity: EntityDefinition) -> None: self.validate(entity); self._items[entity.name] = entity
    def unregister(self, name: str) -> None: self._items.pop(name, None)
    def get(self, name: str) -> EntityDefinition | None: return self._items.get(name)
    def exists(self, name: str) -> bool: return name in self._items
    def list(self) -> list[EntityDefinition]: return list(self._items.values())
    def names(self) -> list[str]: return sorted(self._items)
    def normalize_and_validate(self, entities: list[Entity]) -> list[Entity]:
        result = []
        for entity in entities:
            definition = self._items.get(entity.name)
            if definition is None: continue
            value = definition.normalize(entity.value)
            if definition.validate(value): result.append(Entity(entity.name, value, entity.confidence, entity.start, entity.end, {**entity.metadata, **definition.metadata}))
        return result
