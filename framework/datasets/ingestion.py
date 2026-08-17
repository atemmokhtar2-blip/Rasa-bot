from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, Iterable, Iterator, Protocol, TextIO

from framework.datasets.system import ConversationExample, ConversationTurn, EntityAnnotation, TrainingExample


class DataSource(Protocol):
    """A source that can be consumed incrementally without loading all data."""

    def records(self, *, chunk_size: int = 1000) -> Iterator[dict[str, Any]]: ...


class DataLoader(Protocol):
    def load(self, source: str | bytes | TextIO, *, chunk_size: int = 1000) -> Iterator[dict[str, Any]]: ...


@dataclass(frozen=True)
class CleaningIssue:
    code: str
    record_index: int
    message: str
    severity: str = "warning"


@dataclass
class CleaningReport:
    input_count: int = 0
    output_count: int = 0
    issues: list[CleaningIssue] = field(default_factory=list)
    exact_duplicates: int = 0
    near_duplicates: list[tuple[int, int, float]] = field(default_factory=list)
    invalid_entities: int = 0
    removed_empty: int = 0

    @property
    def quality_score(self) -> float:
        if not self.input_count:
            return 0.0
        penalty = self.removed_empty + self.exact_duplicates + self.invalid_entities + len(self.issues)
        return round(max(0.0, min(100.0, 100.0 * (1.0 - penalty / max(1, self.input_count * 2)))), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_count": self.input_count,
            "output_count": self.output_count,
            "exact_duplicates": self.exact_duplicates,
            "near_duplicates": len(self.near_duplicates),
            "invalid_entities": self.invalid_entities,
            "removed_empty": self.removed_empty,
            "quality_score": self.quality_score,
            "issues": [issue.__dict__ for issue in self.issues],
        }


class StructuredDataLoader:
    """Streaming loader for framework records; JSONL is processed line by line."""

    def load(self, source: str | bytes | TextIO, *, format: str | None = None, chunk_size: int = 1000) -> Iterator[dict[str, Any]]:
        if hasattr(source, "read"):
            text = source.read()
        elif isinstance(source, bytes):
            text = source.decode("utf-8-sig")
        else:
            text = source
        fmt = (format or self._infer_format(text)).lower()
        if fmt in {"jsonl", "ndjson"}:
            yield from self._jsonl(text)
        elif fmt == "json":
            payload = json.loads(text)
            values = payload.get("examples", payload.get("records", payload)) if isinstance(payload, dict) else payload
            if not isinstance(values, list):
                raise ValueError("JSON dataset must contain a list or examples/records list")
            for item in values:
                if not isinstance(item, dict):
                    raise ValueError("Dataset record must be an object")
                yield item
        elif fmt == "csv":
            yield from csv.DictReader(io.StringIO(text))
        elif fmt in {"yaml", "yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("YAML ingestion requires PyYAML") from exc
            payload = yaml.safe_load(text)
            values = payload.get("examples", payload.get("records", payload)) if isinstance(payload, dict) else payload
            if not isinstance(values, list):
                raise ValueError("YAML dataset must contain a list or examples/records list")
            yield from (item for item in values if isinstance(item, dict))
        else:
            raise ValueError(f"Unsupported dataset format: {fmt}")

    @staticmethod
    def _infer_format(text: str) -> str:
        stripped = text.lstrip()
        if "\n" in stripped and all(line.lstrip().startswith("{") for line in stripped.splitlines() if line.strip()):
            return "jsonl"
        if stripped.startswith("{") or stripped.startswith("["):
            return "json"
        if stripped.startswith("---") or re.search(r"^\s*(examples|records):", stripped):
            return "yaml"
        return "csv"

    @staticmethod
    def _jsonl(text: str) -> Iterator[dict[str, Any]]:
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL record at line {line_number} must be an object")
            yield value


class ArabicNormalizer:
    """Conservative Arabic-aware normalizer; transformations are configurable."""

    ALEF_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})

    def __init__(self, *, unify_alef: bool = True, remove_tatweel: bool = True, remove_diacritics: bool = False, collapse_whitespace: bool = True, normalize_punctuation: bool = False):
        self.unify_alef = unify_alef
        self.remove_tatweel = remove_tatweel
        self.remove_diacritics = remove_diacritics
        self.collapse_whitespace = collapse_whitespace
        self.normalize_punctuation = normalize_punctuation

    def normalize(self, text: str) -> str:
        value = unicodedata.normalize("NFKC", str(text).replace("\ufffd", ""))
        if self.unify_alef:
            value = value.translate(self.ALEF_VARIANTS)
        if self.remove_tatweel:
            value = value.replace("ـ", "")
        if self.remove_diacritics:
            value = "".join(char for char in value if unicodedata.category(char) != "Mn")
        if self.normalize_punctuation:
            value = re.sub(r"[،,؛;]+", " ", value)
        return " ".join(value.split()) if self.collapse_whitespace else value


class MassiveDatasetCleaner:
    """Incremental cleaning and validation without blind near-duplicate deletion."""

    def __init__(self, *, normalizer: ArabicNormalizer | None = None, near_duplicate_threshold: float = 0.94):
        self.normalizer = normalizer or ArabicNormalizer()
        self.near_duplicate_threshold = near_duplicate_threshold

    def clean(self, records: Iterable[dict[str, Any]], *, known_intents: set[str] | None = None, known_entities: set[str] | None = None, preserve_near_duplicates: bool = True) -> tuple[list[TrainingExample], CleaningReport]:
        known_intents = known_intents or set()
        known_entities = known_entities or set()
        report = CleaningReport()
        output: list[TrainingExample] = []
        exact_seen: set[tuple[str, str]] = set()
        normalized_texts: list[str] = []
        for index, record in enumerate(records):
            report.input_count += 1
            text = self.normalizer.normalize(str(record.get("text", "")))
            intent = str(record.get("intent", "")).strip()
            if not text:
                report.removed_empty += 1
                report.issues.append(CleaningIssue("EMPTY_SAMPLE", index, "text is empty", "error"))
                continue
            if known_intents and intent not in known_intents:
                report.issues.append(CleaningIssue("UNKNOWN_INTENT", index, intent, "error"))
            entities = tuple(record.get("entities", ()) or ())
            parsed_entities: list[dict[str, Any]] = []
            for raw in entities:
                annotation = EntityAnnotation.from_dict(dict(raw))
                invalid = (not annotation.entity_type or (known_entities and annotation.entity_type not in known_entities) or (annotation.start is not None and (annotation.end is None or annotation.start < 0 or annotation.end <= annotation.start or annotation.end > len(text))))
                if invalid:
                    report.invalid_entities += 1
                    report.issues.append(CleaningIssue("INVALID_ENTITY", index, annotation.entity_type, "error"))
                    continue
                parsed_entities.append(annotation.to_dict())
            key = (text, intent)
            if key in exact_seen:
                report.exact_duplicates += 1
                report.issues.append(CleaningIssue("EXACT_DUPLICATE", index, "duplicate retained only once"))
                continue
            exact_seen.add(key)
            for previous_index, previous_text in enumerate(normalized_texts):
                ratio = SequenceMatcher(None, previous_text, text).ratio()
                if ratio >= self.near_duplicate_threshold and previous_text != text:
                    report.near_duplicates.append((previous_index, index, round(ratio, 4)))
                    report.issues.append(CleaningIssue("NEAR_DUPLICATE", index, f"similarity={ratio:.4f}"))
                    break
            normalized_texts.append(text)
            output.append(TrainingExample(text=text, intent=intent, entities=tuple(parsed_entities), metadata=dict(record.get("metadata", {})), language=str(record.get("language", "ar")), source=str(record.get("source", "imported")), raw_text=str(record.get("text", "")), normalized_text=text, conversation_id=record.get("conversation_id"), difficulty=str(record.get("difficulty", "medium")), import_batch=record.get("import_batch")))
        report.output_count = len(output)
        return output, report


def records_to_conversations(records: Iterable[dict[str, Any]]) -> tuple[ConversationExample, ...]:
    grouped: dict[str, list[ConversationTurn]] = {}
    languages: dict[str, str] = {}
    for record in records:
        conversation_id = record.get("conversation_id")
        if not conversation_id:
            continue
        grouped.setdefault(str(conversation_id), []).append(ConversationTurn(role=str(record.get("role", "user")), text=str(record.get("text", "")), intent=record.get("intent"), entities=tuple(record.get("entities", ()) or ()), expected_action=record.get("expected_action"), expected_state=record.get("expected_state"), metadata=dict(record.get("context", record.get("metadata", {})) or {})))
        languages[str(conversation_id)] = str(record.get("language", "ar"))
    return tuple(ConversationExample(key, tuple(turns), languages.get(key, "ar")) for key, turns in grouped.items())


def content_fingerprint(example: TrainingExample) -> str:
    payload = f"{example.normalized_text or example.text}\0{example.intent}\0{example.language}"
    return sha256(payload.encode("utf-8")).hexdigest()
