from dataclasses import dataclass
from typing import Any
from framework.core.models import Entity, IntentPrediction

@dataclass
class EvaluationResult:
    model_id: str
    model_version: str
    intent_accuracy: float
    entity_accuracy: float
    fallback_rate: float
    action_success_rate: float
    confidence_distribution: dict[str, int]
    samples: int

class EvaluationEngine:
    def evaluate(self, model_id: str, model_version: str, samples: list[dict[str, Any]]) -> EvaluationResult:
        if not samples: raise ValueError("Evaluation data cannot be empty")
        intent_hits = entity_hits = fallback = action_success = 0
        confidence_distribution = {"high": 0, "medium": 0, "low": 0}
        for sample in samples:
            prediction: IntentPrediction = sample["prediction"]
            if prediction.name == sample.get("expected_intent"): intent_hits += 1
            expected_entities = sample.get("expected_entities", {})
            predicted_entities: list[Entity] = sample.get("entities", [])
            actual = {e.name: e.value for e in predicted_entities}
            if actual == expected_entities: entity_hits += 1
            if prediction.name == "fallback": fallback += 1
            if sample.get("action_success") is True: action_success += 1
            if prediction.confidence >= .8: confidence_distribution["high"] += 1
            elif prediction.confidence >= .55: confidence_distribution["medium"] += 1
            else: confidence_distribution["low"] += 1
        total = len(samples)
        return EvaluationResult(model_id, model_version, intent_hits / total, entity_hits / total, fallback / total, action_success / total, confidence_distribution, total)
