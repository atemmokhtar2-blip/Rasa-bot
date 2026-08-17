from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable

from framework.learning.continuous import CandidateSample, InteractionRecord


@dataclass(frozen=True)
class SampleQuality:
    sample_id: str
    completeness: float
    correctness: float
    consistency: float
    duplication: float
    diversity: float
    annotation_quality: float
    intent_balance: float
    entity_quality: float
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetQuality:
    total: int
    completeness: float
    correctness: float
    consistency: float
    duplication: float
    diversity: float
    annotation_quality: float
    intent_balance: float
    entity_quality: float
    score: float
    warnings: tuple[str, ...] = ()


class DataQualityEngine:
    def sample(self, candidate: CandidateSample, *, known_intents: set[str] | None = None, known_entities: set[str] | None = None) -> SampleQuality:
        known_intents = known_intents or set(); known_entities = known_entities or set()
        completeness = 1.0 if candidate.text.strip() and candidate.language else 0.0
        correctness = 1.0 if candidate.suggested_intent and (not known_intents or candidate.suggested_intent in known_intents) else 0.0
        entity_quality = 1.0 if all(item.get("entity_type") and (not known_entities or item.get("entity_type") in known_entities) for item in candidate.entities) else 0.0
        consistency = 1.0 if candidate.sample_status.value in {"pending_review", "approved", "promoted"} else 0.5
        diversity = min(1.0, len(set(candidate.text.split())) / max(1, min(10, len(candidate.text.split()))))
        duplication = 1.0 if candidate.status.value != "duplicate" else 0.0
        annotation = 1.0 if candidate.suggested_intent else 0.0
        balance = 1.0
        score = round(100 * sum((completeness, correctness, consistency, duplication, diversity, annotation, balance, entity_quality)) / 8, 2)
        reasons = tuple(code for code, value in (("missing_text", completeness), ("unknown_intent", correctness), ("invalid_entities", entity_quality), ("duplicate", duplication)) if value == 0)
        return SampleQuality(candidate.sample_id, completeness, correctness, consistency, duplication, diversity, annotation, balance, entity_quality, score, reasons)

    def dataset(self, candidates: Iterable[CandidateSample]) -> DatasetQuality:
        rows = list(candidates)
        if not rows: return DatasetQuality(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ("empty_dataset",))
        intents = Counter(item.suggested_intent for item in rows); lengths = [len(item.text) for item in rows]; quality = [self.sample(item) for item in rows]
        min_count = min(intents.values()); max_count = max(intents.values()); balance = min_count / max_count if max_count else 0
        diversity = min(1.0, len(set(item.text for item in rows)) / len(rows)); duplicate = sum(item.status.value == "duplicate" for item in rows); duplication = 1 - duplicate / len(rows)
        values = [sum(getattr(item, field) for field in ("completeness", "correctness", "consistency", "annotation_quality", "entity_quality")) / 5 for item in quality]
        warnings = []
        if balance < 0.1: warnings.append("intent_imbalance")
        if diversity < 0.3: warnings.append("low_diversity")
        return DatasetQuality(len(rows), sum(item.completeness for item in quality) / len(rows), sum(item.correctness for item in quality) / len(rows), sum(item.consistency for item in quality) / len(rows), duplication, diversity, sum(item.annotation_quality for item in quality) / len(rows), balance, sum(item.entity_quality for item in quality) / len(rows), round(100 * sum(values) / len(values), 2), tuple(warnings))


@dataclass(frozen=True)
class HardExample:
    interaction_id: str
    reason: str
    severity: str
    cluster_key: str


class HardExampleEngine:
    def detect(self, interactions: Iterable[InteractionRecord], *, known_correct_intents: dict[str, str] | None = None, threshold: float = 0.55) -> list[HardExample]:
        known_correct_intents = known_correct_intents or {}; result = []
        for item in interactions:
            if item.interaction_id in known_correct_intents and known_correct_intents[item.interaction_id] != item.predicted_intent:
                reason = "high_confidence_error" if (item.confidence or 0) >= 0.9 else "intent_error"; severity = "critical" if reason == "high_confidence_error" else "high"
                result.append(HardExample(item.interaction_id, reason, severity, f"{known_correct_intents[item.interaction_id]}_vs_{item.predicted_intent}"))
            elif item.confidence is not None and item.confidence < threshold:
                result.append(HardExample(item.interaction_id, "low_confidence", "medium", item.predicted_intent or "unknown"))
        return result

    def cluster(self, examples: Iterable[HardExample]) -> dict[str, list[str]]:
        clusters: dict[str, list[str]] = defaultdict(list)
        for item in examples: clusters[item.cluster_key].append(item.interaction_id)
        return dict(clusters)
