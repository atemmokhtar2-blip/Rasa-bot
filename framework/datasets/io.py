from __future__ import annotations
import csv
import io
import json
from dataclasses import asdict
from typing import Any, Iterable, Protocol
from framework.datasets.system import ConversationExample, ConversationTurn, DatasetVersion, EntityAnnotation, TrainingExample
from framework.datasets.ingestion import StructuredDataLoader, records_to_conversations

class DatasetImporter(Protocol):
    def import_data(self, payload: str | bytes, *, project_id: str, dataset_id: str, version: str, language: str = 'ar', created_by: str | None = None) -> DatasetVersion: ...
    def iter_data(self, payload: str | bytes, *, language: str = 'ar', created_by: str | None = None): ...


class StreamingDatasetImporter:
    """Chunk-friendly importer facade; callers can consume records incrementally."""
    def __init__(self, loader: StructuredDataLoader | None = None): self.loader = loader or StructuredDataLoader()
    def iter_data(self, payload: str | bytes, *, format: str | None = None, language: str = 'ar', created_by: str | None = None):
        for record in self.loader.load(payload, format=format):
            yield _example(record, language, created_by)
    def import_data(self, payload: str | bytes, *, project_id: str, dataset_id: str, version: str, language: str = 'ar', created_by: str | None = None, format: str | None = None) -> DatasetVersion:
        examples = tuple(self.iter_data(payload, format=format, language=language, created_by=created_by))
        records = [{"conversation_id": item.conversation_id, "text": item.text, "intent": item.intent, "entities": list(item.entities), "language": item.language} for item in examples if item.conversation_id]
        return DatasetVersion(dataset_id, version, project_id, examples, conversations=records_to_conversations(records), created_by=created_by)

class DatasetExporter(Protocol):
    def export(self, dataset: DatasetVersion) -> dict[str, Any]: ...

def _example(item: dict[str, Any], language: str, created_by: str | None) -> TrainingExample:
    entities = tuple(item.get('entities', ()))
    return TrainingExample(text=str(item.get('text', '')), intent=str(item.get('intent', '')), entities=entities, metadata=dict(item.get('metadata', {})), language=str(item.get('language', language)), source=str(item.get('source', 'imported')), created_by=created_by, conversation_id=item.get('conversation_id'))

class JSONImporter:
    def import_data(self, payload, *, project_id, dataset_id, version, language='ar', created_by=None):
        data = json.loads(payload.decode() if isinstance(payload, bytes) else payload); items = data.get('examples', data) if isinstance(data, dict) else data
        return DatasetVersion(dataset_id, version, project_id, tuple(_example(item, language, created_by) for item in items))

class JSONLImporter:
    def import_data(self, payload, *, project_id, dataset_id, version, language='ar', created_by=None):
        text = payload.decode() if isinstance(payload, bytes) else payload
        return DatasetVersion(dataset_id, version, project_id, tuple(_example(json.loads(line), language, created_by) for line in text.splitlines() if line.strip()))

class CSVImporter:
    def import_data(self, payload, *, project_id, dataset_id, version, language='ar', created_by=None):
        text = payload.decode() if isinstance(payload, bytes) else payload; rows = csv.DictReader(io.StringIO(text))
        return DatasetVersion(dataset_id, version, project_id, tuple(_example(dict(row), language, created_by) for row in rows))

class FrameworkJSONExporter:
    def export(self, dataset: DatasetVersion) -> dict[str, Any]:
        return {"dataset_id": dataset.dataset_id, "version": dataset.version, "project_id": dataset.project_id, "schema_version": dataset.schema_version, "checksum": dataset.checksum or dataset.calculate_checksum(), "examples": [{"example_id": e.example_id, "text": e.text, "intent": e.intent, "entities": list(e.entities), "language": e.language, "metadata": e.metadata, "source": e.source} for e in dataset.examples], "conversations": [{"conversation_id": c.conversation_id, "language": c.language, "turns": [asdict(turn) for turn in c.turns]} for c in dataset.conversations]}

class RasaExporter:
    def __init__(self, rasa_version: str = '3.x', schema_version: str = '3.1'): self.rasa_version, self.schema_version = rasa_version, schema_version
    def export(self, dataset: DatasetVersion) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for example in dataset.examples:
            entities = []
            for raw in example.entities:
                item = EntityAnnotation.from_dict(raw); entities.append({"entity": item.entity_type, "value": item.value, "start": item.start, "end": item.end, **({"role": item.role} if item.role else {}), **({"group": item.group} if item.group else {})})
            grouped.setdefault(example.intent, []).append({"text": example.text, "entities": entities})
        nlu = {"version": self.schema_version, "nlu": [{"intent": intent, "examples": "\n".join(f"- {item['text']}" for item in items)} for intent, items in sorted(grouped.items())]}
        stories = {"version": self.schema_version, "stories": [{"story": conversation.conversation_id, "steps": [{"intent": turn.intent} if turn.role == 'user' and turn.intent else {"action": turn.expected_action} for turn in conversation.turns if turn.intent or turn.expected_action]} for conversation in dataset.conversations]}
        domain = {"version": self.schema_version, "intents": sorted(grouped), "entities": sorted({EntityAnnotation.from_dict(raw).entity_type for item in dataset.examples for raw in item.entities}), "responses": {}}
        return {"rasa_version": self.rasa_version, "schema_version": self.schema_version, "nlu.yml": nlu, "stories.yml": stories, "domain.yml": domain}
