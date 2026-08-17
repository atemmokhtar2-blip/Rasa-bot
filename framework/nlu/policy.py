from dataclasses import dataclass
from typing import Any
from framework.core.models import Entity, IntentPrediction, NLUResult

@dataclass(frozen=True)
class ConfidenceDecision:
    status: str
    reason: str

class ConfidencePolicy:
    def __init__(self, high_threshold: float = 0.80, low_threshold: float = 0.55):
        if not 0 <= low_threshold <= high_threshold <= 1: raise ValueError("confidence thresholds must satisfy 0 <= low <= high <= 1")
        self.high_threshold, self.low_threshold = high_threshold, low_threshold
    def classify(self, confidence: float) -> ConfidenceDecision:
        if confidence >= self.high_threshold: return ConfidenceDecision("accept", "high_confidence")
        if confidence >= self.low_threshold: return ConfidenceDecision("clarify", "medium_confidence")
        return ConfidenceDecision("fallback", "low_confidence")
    def apply_optimized_thresholds(self, optimized: dict[str, Any]) -> None:
        accept = float(optimized["accept_threshold"]); clarify = float(optimized["clarification_threshold"]); fallback = float(optimized["fallback_threshold"])
        if not 0 <= fallback <= clarify <= accept <= 1: raise ValueError("optimized thresholds must satisfy 0 <= fallback <= clarify <= accept <= 1")
        self.high_threshold, self.low_threshold = accept, clarify

class IntentResolver:
    def resolve(self, result: NLUResult) -> IntentPrediction: return result.intent

class EntityNormalizer:
    def __init__(self, normalizers: dict[str, Any] | None = None): self.normalizers = normalizers or {}
    def normalize(self, entities: list[Entity], metadata: dict[str, Any] | None = None) -> list[Entity]:
        result = []
        for entity in entities:
            normalizer = self.normalizers.get(entity.name)
            value = normalizer(entity.value, metadata or {}) if normalizer else entity.value
            result.append(Entity(entity.name, value, entity.confidence, entity.start, entity.end, dict(entity.metadata)))
        return result
