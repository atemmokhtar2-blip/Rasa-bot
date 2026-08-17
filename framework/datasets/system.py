from __future__ import annotations
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Iterable
from uuid import uuid4

class DatasetStatus(str, Enum): DRAFT = "draft"; VALIDATING = "validating"; READY = "ready"; ARCHIVED = "archived"; FAILED = "failed"
class VersionStatus(str, Enum): DRAFT = "draft"; VALIDATING = "validating"; PUBLISHED = "published"; FAILED = "failed"; ARCHIVED = "archived"
class ReviewStatus(str, Enum): UNREVIEWED = "unreviewed"; APPROVED = "approved"; REJECTED = "rejected"; NEEDS_REVIEW = "needs_review"

@dataclass(frozen=True)
class EntityAnnotation:
    entity_type: str
    value: Any
    start: int | None = None
    end: int | None = None
    role: str | None = None
    group: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EntityAnnotation":
        return cls(str(value.get("entity_type", value.get("entity", ""))), value.get("value"), value.get("start"), value.get("end"), value.get("role"), value.get("group"), value.get("confidence"), dict(value.get("metadata", {})))
    def to_dict(self) -> dict[str, Any]: return {"entity_type": self.entity_type, "value": self.value, "start": self.start, "end": self.end, "role": self.role, "group": self.group, "confidence": self.confidence, "metadata": self.metadata}

@dataclass(frozen=True)
class TrainingExample:
    text: str
    intent: str
    entities: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    language: str = "ar"
    source: str = "manual"
    example_id: str = field(default_factory=lambda: str(uuid4()))
    raw_text: str | None = None
    normalized_text: str | None = None
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    created_by: str | None = None
    import_batch: str | None = None
    conversation_id: str | None = None
    difficulty: str = "medium"
    def annotations(self) -> tuple[EntityAnnotation, ...]: return tuple(EntityAnnotation.from_dict(item) for item in self.entities)
    def with_normalized_text(self, value: str) -> "TrainingExample": return replace(self, raw_text=self.raw_text or self.text, normalized_text=value)

@dataclass(frozen=True)
class ConversationTurn:
    role: str
    text: str
    intent: str | None = None
    entities: tuple[dict[str, Any], ...] = ()
    expected_action: str | None = None
    expected_state: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ConversationExample:
    conversation_id: str
    turns: tuple[ConversationTurn, ...]
    language: str = "ar"
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    project_id: str
    name: str
    description: str = ""
    language: str = "ar"
    status: DatasetStatus = DatasetStatus.DRAFT
    schema_version: str = "1.0"
    current_version: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    def archive(self) -> "Dataset": return replace(self, status=DatasetStatus.ARCHIVED, updated_at=datetime.now(timezone.utc))

@dataclass(frozen=True)
class DatasetVersion:
    dataset_id: str
    version: str
    project_id: str
    examples: tuple[TrainingExample, ...]
    schema_version: str = "1.0"
    status: str = "draft"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    conversations: tuple[ConversationExample, ...] = ()
    created_by: str | None = None
    statistics: dict[str, Any] = field(default_factory=dict)
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    def content_payload(self) -> dict[str, Any]:
        return {"dataset_id": self.dataset_id, "version": self.version, "project_id": self.project_id, "schema_version": self.schema_version, "examples": [{"id": e.example_id, "text": e.text, "intent": e.intent, "entities": list(e.entities), "language": e.language, "metadata": e.metadata, "source": e.source, "conversation_id": e.conversation_id} for e in self.examples], "conversations": [{"conversation_id": c.conversation_id, "turns": [turn.__dict__ for turn in c.turns], "language": c.language} for c in self.conversations]}
    def calculate_checksum(self) -> str: return hashlib.sha256(json.dumps(self.content_payload(), ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    def published(self) -> "DatasetVersion": return replace(self, status=VersionStatus.PUBLISHED.value, checksum=self.checksum or self.calculate_checksum())

class DatasetValidator:
    allowed_languages = {"ar", "en", "arabizi", "mixed"}
    def validate(self, examples: list[TrainingExample], known_intents: set[str], known_entities: set[str], languages: set[str] | None = None) -> list[str]:
        errors: list[str] = []; seen: set[tuple[str, str]] = set(); languages = languages or self.allowed_languages
        for index, example in enumerate(examples):
            if not example.text.strip(): errors.append(f"example[{index}].text is empty")
            if not example.intent: errors.append(f"example[{index}].intent is missing")
            if known_intents and example.intent not in known_intents: errors.append(f"example[{index}].intent is unknown")
            if example.language not in languages: errors.append(f"example[{index}].language is invalid")
            key = (example.text.strip(), example.intent)
            if key in seen: errors.append(f"example[{index}] is duplicate")
            seen.add(key)
            for entity in example.annotations():
                if known_entities and entity.entity_type not in known_entities: errors.append(f"example[{index}] has unknown entity")
                if entity.start is not None and (entity.start < 0 or entity.end is None or entity.end < entity.start or entity.end > len(example.text)): errors.append(f"example[{index}] has invalid entity positions")
        return errors

class DatasetRegistry:
    def __init__(self): self._datasets: dict[str, Dataset] = {}; self._versions: dict[tuple[str, str], DatasetVersion] = {}
    def create(self, project_id: str, name: str, description: str = "", language: str = "ar", metadata: dict[str, Any] | None = None) -> Dataset:
        dataset = Dataset(str(uuid4()), project_id, name, description, language, metadata=metadata or {})
        self._datasets[dataset.dataset_id] = dataset; return dataset
    def get_dataset(self, dataset_id: str, project_id: str | None = None) -> Dataset | None:
        dataset = self._datasets.get(dataset_id)
        return dataset if dataset and (project_id is None or dataset.project_id == project_id) else None
    def list_project(self, project_id: str) -> list[Dataset]: return [item for item in self._datasets.values() if item.project_id == project_id]
    def create_version(self, dataset_id: str, version: str, examples: Iterable[TrainingExample], *, conversations: Iterable[ConversationExample] = (), created_by: str | None = None, metadata: dict[str, Any] | None = None) -> DatasetVersion:
        dataset = self._datasets[dataset_id]
        key = (dataset_id, version)
        if key in self._versions: raise ValueError("Dataset version already exists")
        return DatasetVersion(dataset_id, version, dataset.project_id, tuple(examples), dataset.schema_version, VersionStatus.DRAFT.value, created_by=created_by, conversations=tuple(conversations), metadata=metadata or {})
    def publish(self, dataset: DatasetVersion) -> DatasetVersion:
        key = (dataset.dataset_id, dataset.version)
        if key in self._versions: raise ValueError("Published dataset version is immutable")
        published = dataset.published(); self._versions[key] = published
        current = self._datasets.get(dataset.dataset_id)
        if current: self._datasets[dataset.dataset_id] = replace(current, current_version=dataset.version, status=DatasetStatus.READY, updated_at=datetime.now(timezone.utc))
        return published
    def get(self, dataset_id: str, version: str) -> DatasetVersion | None: return self._versions.get((dataset_id, version))
    def list_versions(self, dataset_id: str) -> list[DatasetVersion]: return sorted([v for (d, _), v in self._versions.items() if d == dataset_id], key=lambda item: item.version)
