from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass, field
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
    intent_precision: float = 0.0
    intent_recall: float = 0.0
    intent_f1: float = 0.0
    entity_precision: float = 0.0
    entity_recall: float = 0.0
    entity_f1: float = 0.0
    per_intent: dict[str, dict[str, float]] = field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    confidence_correctness: dict[str, float] = field(default_factory=dict)
    hard_set: bool = False
    regression_passed: bool | None = None
    optimized_thresholds: dict[str, Any] | None = None
    def to_dict(self) -> dict[str, Any]: return self.__dict__.copy()

@dataclass(frozen=True)
class QualityGate:
    min_intent_f1: float = 0.0
    min_entity_f1: float = 0.0
    max_fallback_rate: float = 1.0
    require_artifact: bool = True
    def check(self, result: EvaluationResult, artifact_uri: str | None = None, training_succeeded: bool = True) -> tuple[bool, list[str]]:
        failures = []
        if not training_succeeded: failures.append("training_failed")
        if result.intent_f1 < self.min_intent_f1: failures.append("intent_f1_below_threshold")
        if result.entity_f1 < self.min_entity_f1: failures.append("entity_f1_below_threshold")
        if result.fallback_rate > self.max_fallback_rate: failures.append("fallback_rate_above_threshold")
        if self.require_artifact and not artifact_uri: failures.append("artifact_missing")
        return not failures, failures

class EvaluationEngine:
    def evaluate(self, model_id: str, model_version: str, samples: list[dict[str, Any]], *, hard_set: bool = False, regression_baseline: EvaluationResult | None = None, optimize_thresholds: bool = False) -> EvaluationResult:
        if not samples: raise ValueError("Evaluation data cannot be empty")
        intent_hits = entity_hits = fallback = action_success = 0; confidence_distribution = {"high": 0, "medium": 0, "low": 0}; confusion: dict[str, Counter[str]] = defaultdict(Counter); by_intent: dict[str, Counter[str]] = defaultdict(Counter); confidence_bins: dict[str, list[bool]] = defaultdict(list); entity_tp = entity_fp = entity_fn = 0
        for sample in samples:
            prediction: IntentPrediction = sample["prediction"]; expected = str(sample.get("expected_intent", "fallback")); actual_intent = prediction.name
            if actual_intent == expected: intent_hits += 1
            confusion[expected][actual_intent] += 1; by_intent[expected]["support"] += 1; by_intent[expected]["tp"] += int(actual_intent == expected); by_intent[actual_intent]["fp"] += int(actual_intent != expected)
            expected_entities = sample.get("expected_entities", {}); predicted_entities: list[Entity] = sample.get("entities", []); actual_entities = {e.name: e.value for e in predicted_entities}; expected_entities = dict(expected_entities)
            entity_hits += int(actual_entities == expected_entities); entity_tp += sum(1 for key, value in actual_entities.items() if expected_entities.get(key) == value); entity_fp += sum(1 for key, value in actual_entities.items() if expected_entities.get(key) != value); entity_fn += sum(1 for key, value in expected_entities.items() if actual_entities.get(key) != value)
            fallback += int(actual_intent == "fallback"); action_success += int(sample.get("action_success") is True)
            level = "high" if prediction.confidence >= .8 else "medium" if prediction.confidence >= .55 else "low"; confidence_distribution[level] += 1; confidence_bins[level].append(actual_intent == expected)
        total = len(samples); predicted_total = sum(sum(counter.values()) for counter in confusion.values()); precision = intent_hits / predicted_total if predicted_total else 0.0; recall = intent_hits / total; f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0; entity_precision = entity_tp / (entity_tp + entity_fp) if entity_tp + entity_fp else 1.0; entity_recall = entity_tp / (entity_tp + entity_fn) if entity_tp + entity_fn else 1.0; entity_f1 = 2 * entity_precision * entity_recall / (entity_precision + entity_recall) if entity_precision + entity_recall else 0.0
        per_intent = {}
        for intent, counts in by_intent.items():
            support = counts["support"]; tp = counts["tp"]; fp = counts["fp"]; fn = support - tp; p = tp / (tp + fp) if tp + fp else 0.0; r = tp / support if support else 0.0; per_intent[intent] = {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "support": support}
        confidence_correctness = {level: sum(values) / len(values) for level, values in confidence_bins.items() if values}; regression = None if regression_baseline is None else f1 >= regression_baseline.intent_f1 and entity_f1 >= regression_baseline.entity_f1
        optimized = None
        if optimize_thresholds:
            from framework.models.thresholds import ThresholdOptimizer
            optimized = ThresholdOptimizer().optimize(samples).to_dict()
        return EvaluationResult(model_id, model_version, intent_hits / total, entity_hits / total, fallback / total, action_success / total, confidence_distribution, total, precision, recall, f1, entity_precision, entity_recall, entity_f1, per_intent, {key: dict(value) for key, value in confusion.items()}, confidence_correctness, hard_set, regression, optimized)
