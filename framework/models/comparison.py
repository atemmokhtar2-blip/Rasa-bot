from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from framework.models.evaluation import EvaluationResult

@dataclass(frozen=True)
class ModelComparisonEntry:
    model_id: str
    model_version: str
    score: float
    intent_f1: float
    entity_f1: float
    fallback_rate: float
    regression_passed: bool | None
    rank: int = 0
    def to_dict(self) -> dict[str, Any]: return self.__dict__.copy()

@dataclass(frozen=True)
class ModelComparisonResult:
    metric_weights: dict[str, float]
    entries: tuple[ModelComparisonEntry, ...]
    winner_model_id: str | None
    winner_model_version: str | None
    compared_at: str
    def to_dict(self) -> dict[str, Any]: return {"metric_weights": self.metric_weights, "entries": [entry.to_dict() for entry in self.entries], "winner_model_id": self.winner_model_id, "winner_model_version": self.winner_model_version, "compared_at": self.compared_at}

class ModelComparator:
    def __init__(self, *, intent_f1_weight: float = 0.5, entity_f1_weight: float = 0.3, fallback_weight: float = 0.2):
        total = intent_f1_weight + entity_f1_weight + fallback_weight
        if total <= 0 or min(intent_f1_weight, entity_f1_weight, fallback_weight) < 0: raise ValueError("comparison weights must be non-negative and non-zero")
        self.weights = {"intent_f1": intent_f1_weight / total, "entity_f1": entity_f1_weight / total, "fallback_rate": fallback_weight / total}

    def score(self, result: EvaluationResult) -> float:
        return self.weights["intent_f1"] * result.intent_f1 + self.weights["entity_f1"] * result.entity_f1 + self.weights["fallback_rate"] * (1.0 - result.fallback_rate)

    def compare(self, results: list[EvaluationResult], *, require_regression_pass: bool = False) -> ModelComparisonResult:
        if not results: raise ValueError("At least one model evaluation is required")
        eligible = [result for result in results if not require_regression_pass or result.regression_passed is True]
        ranked = sorted(eligible, key=lambda result: (self.score(result), result.intent_f1, result.entity_f1, -result.fallback_rate), reverse=True)
        entries = tuple(ModelComparisonEntry(result.model_id, result.model_version, self.score(result), result.intent_f1, result.entity_f1, result.fallback_rate, result.regression_passed, index + 1) for index, result in enumerate(ranked))
        winner = entries[0] if entries else None
        from datetime import datetime, timezone
        return ModelComparisonResult(self.weights, entries, winner.model_id if winner else None, winner.model_version if winner else None, datetime.now(timezone.utc).isoformat())

__all__ = ["ModelComparisonEntry", "ModelComparisonResult", "ModelComparator"]
