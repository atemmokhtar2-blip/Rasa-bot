from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

@dataclass(frozen=True)
class TrainingExample:
    text: str
    intent: str
    entities: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class DatasetVersion:
    dataset_id: str
    version: str
    project_id: str
    examples: tuple[TrainingExample, ...]
    schema_version: str = "1.0"
    status: str = "draft"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class DatasetValidator:
    def validate(self, examples: list[TrainingExample], known_intents: set[str], known_entities: set[str]) -> list[str]:
        errors: list[str] = []
        seen: set[tuple[str, str]] = set()
        for index, example in enumerate(examples):
            if not example.text.strip(): errors.append(f"example[{index}].text is empty")
            if example.intent not in known_intents: errors.append(f"example[{index}].intent is unknown")
            key = (example.text.strip(), example.intent)
            if key in seen: errors.append(f"example[{index}] is duplicate")
            seen.add(key)
            for entity in example.entities:
                if entity.get("entity") not in known_entities: errors.append(f"example[{index}] has unknown entity")
        return errors

class DatasetRegistry:
    def __init__(self): self._versions: dict[tuple[str, str], DatasetVersion] = {}
    def publish(self, dataset: DatasetVersion) -> DatasetVersion:
        key = (dataset.dataset_id, dataset.version)
        if key in self._versions: raise ValueError("Published dataset version is immutable")
        published = DatasetVersion(dataset.dataset_id, dataset.version, dataset.project_id, dataset.examples, dataset.schema_version, "published", dataset.created_at)
        self._versions[key] = published
        return published
    def get(self, dataset_id: str, version: str) -> DatasetVersion | None: return self._versions.get((dataset_id, version))
