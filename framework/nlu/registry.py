from dataclasses import dataclass, field
from typing import Any, Callable
from framework.core.models import Entity

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
    def register(self, intent: IntentDefinition) -> None: self._items[intent.name] = intent
    def resolve(self, name: str) -> IntentDefinition | None: return self._items.get(name)
    def names(self) -> list[str]: return sorted(self._items)

class EntityRegistry:
    def __init__(self): self._items: dict[str, EntityDefinition] = {}
    def register(self, entity: EntityDefinition) -> None: self._items[entity.name] = entity
    def names(self) -> list[str]: return sorted(self._items)
    def normalize_and_validate(self, entities: list[Entity]) -> list[Entity]:
        result = []
        for entity in entities:
            definition = self._items.get(entity.name)
            if definition is None: continue
            value = definition.normalize(entity.value)
            if definition.validate(value): result.append(Entity(entity.name, value, entity.confidence, entity.start, entity.end, {**entity.metadata, **definition.metadata}))
        return result
