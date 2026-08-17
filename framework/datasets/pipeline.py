from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Iterable
from framework.datasets.system import DatasetValidator, DatasetVersion, TrainingExample

@dataclass
class QualityReport:
    total: int
    valid: int
    duplicate_count: int
    intent_distribution: dict[str, int]
    errors: list[str]
    near_duplicate_count: int = 0
    conflict_count: int = 0
    warnings: list[str] = field(default_factory=list)
    statistics: dict[str, object] = field(default_factory=dict)
    quality_score: float = 0.0
    def to_dict(self) -> dict[str, object]: return {"total": self.total, "valid": self.valid, "duplicate_count": self.duplicate_count, "near_duplicate_count": self.near_duplicate_count, "conflict_count": self.conflict_count, "intent_distribution": self.intent_distribution, "errors": self.errors, "warnings": self.warnings, "statistics": self.statistics, "quality_score": self.quality_score}

@dataclass(frozen=True)
class DatasetSplit:
    train: tuple[TrainingExample, ...]
    validation: tuple[TrainingExample, ...]
    test: tuple[TrainingExample, ...]
    seed: int = 42
    def as_dict(self): return {"train": self.train, "validation": self.validation, "test": self.test}

class DatasetPipeline:
    def __init__(self, validator: DatasetValidator | None = None, near_duplicate_threshold: float = 0.92, unicode_normalization: str = "NFKC", normalize_punctuation: bool = False):
        self.validator = validator or DatasetValidator(); self.near_duplicate_threshold = near_duplicate_threshold; self.unicode_normalization = unicode_normalization; self.normalize_punctuation = normalize_punctuation
    def normalize_text(self, text: str) -> str:
        value = unicodedata.normalize(self.unicode_normalization, text); value = " ".join(value.split())
        if self.normalize_punctuation: value = re.sub(r"[،,؛;]+", " ", value); value = " ".join(value.split())
        return value
    def normalize(self, examples: list[TrainingExample]) -> list[TrainingExample]:
        return [replace(example, raw_text=example.raw_text or example.text, normalized_text=self.normalize_text(example.text), text=self.normalize_text(example.text), intent=example.intent.strip()) for example in examples]
    def deduplicate(self, examples: list[TrainingExample]) -> list[TrainingExample]:
        seen: set[tuple[str, str]] = set(); result = []
        for example in examples:
            key = (example.normalized_text or self.normalize_text(example.text), example.intent)
            if key not in seen: seen.add(key); result.append(example)
        return result
    def find_near_duplicates(self, examples: list[TrainingExample]) -> list[tuple[int, int]]:
        pairs = []
        for left in range(len(examples)):
            for right in range(left + 1, len(examples)):
                a = examples[left].normalized_text or self.normalize_text(examples[left].text); b = examples[right].normalized_text or self.normalize_text(examples[right].text)
                if a != b and SequenceMatcher(None, a, b).ratio() >= self.near_duplicate_threshold: pairs.append((left, right))
        return pairs
    def find_conflicts(self, examples: list[TrainingExample]) -> list[dict[str, object]]:
        intents: dict[str, set[str]] = defaultdict(set)
        for example in examples: intents[example.normalized_text or self.normalize_text(example.text)].add(example.intent)
        return [{"text": text, "intents": sorted(values)} for text, values in intents.items() if len(values) > 1]
    def leakage(self, split: DatasetSplit) -> dict[str, object]:
        buckets = {"train": split.train, "validation": split.validation, "test": split.test}; overlaps = []
        normalized = {name: {self.normalize_text(item.text): item.intent for item in values} for name, values in buckets.items()}
        names = list(normalized)
        for left_index, left in enumerate(names):
            for right in names[left_index + 1:]:
                overlap = sorted(set(normalized[left]) & set(normalized[right]))
                overlaps.append({"left": left, "right": right, "count": len(overlap), "examples": overlap[:20]})
        return {"has_leakage": any(item["count"] for item in overlaps), "overlaps": overlaps}
    def statistics(self, examples: list[TrainingExample], duplicate_count: int = 0, conflict_count: int = 0, invalid_count: int = 0) -> dict[str, object]:
        intents = Counter(e.intent for e in examples); languages = Counter(e.language for e in examples); entities = Counter(annotation.entity_type for e in examples for annotation in e.annotations()); lengths = [len(e.text) for e in examples]
        minimum, maximum = (min(lengths), max(lengths)) if lengths else (0, 0); imbalance = max(intents.values()) / max(1, min(intents.values())) if intents else 0.0
        return {"total_examples": len(examples), "total_conversations": len({e.conversation_id for e in examples if e.conversation_id}), "total_intents": len(intents), "total_entities": sum(entities.values()), "entity_distribution": dict(entities), "examples_per_intent": dict(intents), "examples_per_language": dict(languages), "average_text_length": sum(lengths) / len(lengths) if lengths else 0.0, "minimum_text_length": minimum, "maximum_text_length": maximum, "duplicate_count": duplicate_count, "duplicate_ratio": duplicate_count / max(1, len(examples)), "invalid_count": invalid_count, "invalid_ratio": invalid_count / max(1, len(examples)), "conflict_count": conflict_count, "class_imbalance_ratio": imbalance}
    def quality(self, examples: list[TrainingExample], known_intents: set[str], known_entities: set[str]) -> QualityReport:
        normalized = self.normalize(examples); exact_duplicates = len(normalized) - len(self.deduplicate(normalized)); unique = self.deduplicate(normalized); near = self.find_near_duplicates(unique); conflicts = self.find_conflicts(unique); errors = self.validator.validate(unique, known_intents, known_entities); stats = self.statistics(unique, exact_duplicates, len(conflicts), len(errors))
        schema_score = (len(unique) - len(errors)) / len(unique) if unique else 0.0; duplicate_score = max(0.0, 1 - exact_duplicates / len(normalized)) if normalized else 1.0; conflict_score = max(0.0, 1 - len(conflicts) / len(unique)) if unique else 1.0; score = round(100 * (0.5 * schema_score + 0.2 * duplicate_score + 0.2 * conflict_score + 0.1 * (1.0 if unique else 0.0)), 2)
        warnings = [f"near_duplicate:{pair[0]}:{pair[1]}" for pair in near] + [f"conflict:{item['text']}:{item['intents']}" for item in conflicts]
        if stats["class_imbalance_ratio"] >= 10: warnings.append(f"class_imbalance:{stats['class_imbalance_ratio']:.2f}")
        return QualityReport(len(normalized), len(unique) - len(errors), exact_duplicates, dict(Counter(e.intent for e in unique)), errors, len(near), len(conflicts), warnings, stats, score)
    def prepare(self, dataset: DatasetVersion, known_intents: set[str], known_entities: set[str]) -> tuple[DatasetVersion, QualityReport]:
        normalized = self.normalize(list(dataset.examples)); report = self.quality(normalized, known_intents, known_entities)
        if report.errors: raise ValueError(f"Dataset quality checks failed: {report.errors}")
        prepared_examples = tuple(self.deduplicate(normalized))
        prepared = replace(dataset, examples=prepared_examples, status="validated", statistics=report.statistics)
        return replace(prepared, checksum=prepared.calculate_checksum()), report
    def split(self, examples: Iterable[TrainingExample], train_ratio: float = 0.8, validation_ratio: float = 0.1, test_ratio: float = 0.1, seed: int = 42) -> DatasetSplit:
        if any(r < 0 for r in (train_ratio, validation_ratio, test_ratio)) or abs(train_ratio + validation_ratio + test_ratio - 1) > 1e-6: raise ValueError("split ratios must be non-negative and sum to 1")
        import random
        groups: dict[str, list[TrainingExample]] = defaultdict(list)
        for example in examples: groups[example.conversation_id or f"example:{example.example_id}"].append(example)
        grouped = list(groups.values()); random.Random(seed).shuffle(grouped)
        ratios = (train_ratio, validation_ratio, test_ratio); buckets: list[list[TrainingExample]] = [[], [], []]
        total_examples = sum(len(group) for group in grouped); targets = [total_examples * ratio for ratio in ratios]
        intents = Counter(example.intent for group in grouped for example in group); target_intents = [{intent: count * ratio for intent, count in intents.items()} for ratio in ratios]; current_intents = [Counter() for _ in ratios]
        for group in sorted(grouped, key=len, reverse=True):
            group_intents = Counter(example.intent for example in group)
            def score(index: int) -> float:
                size_pressure = max(0.0, (len(buckets[index]) + len(group) - targets[index]))
                intent_pressure = sum(max(0.0, current_intents[index][intent] + count - target_intents[index][intent]) for intent, count in group_intents.items())
                return size_pressure + intent_pressure
            selected = min(range(3), key=score)
            buckets[selected].extend(group); current_intents[selected].update(group_intents)
        return DatasetSplit(tuple(buckets[0]), tuple(buckets[1]), tuple(buckets[2]), seed)
