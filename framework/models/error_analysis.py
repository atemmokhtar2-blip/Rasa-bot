from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from framework.core.models import IntentPrediction


@dataclass(frozen=True)
class ErrorCase:
    index: int
    expected_intent: str
    predicted_intent: str
    confidence: float
    text: str | None = None
    reason: str = "intent_mismatch"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorAnalysisReport:
    total: int
    errors: list[ErrorCase]
    confusion_pairs: dict[str, int]
    low_confidence_cases: list[ErrorCase]
    per_intent_errors: dict[str, int]

    @property
    def error_rate(self) -> float:
        return len(self.errors) / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "error_rate": self.error_rate, "errors": [case.__dict__ for case in self.errors], "confusion_pairs": self.confusion_pairs, "low_confidence_cases": [case.__dict__ for case in self.low_confidence_cases], "per_intent_errors": self.per_intent_errors}


class ErrorAnalyzer:
    def __init__(self, low_confidence_threshold: float = 0.55):
        self.low_confidence_threshold = low_confidence_threshold

    def analyze(self, samples: list[dict[str, Any]]) -> ErrorAnalysisReport:
        errors: list[ErrorCase] = []
        low_confidence: list[ErrorCase] = []
        pairs: Counter[str] = Counter()
        per_intent: Counter[str] = Counter()
        for index, sample in enumerate(samples):
            prediction = sample.get("prediction")
            if not isinstance(prediction, IntentPrediction):
                prediction = IntentPrediction(str(sample.get("predicted_intent", "fallback")), float(sample.get("confidence", 0.0)))
            expected = str(sample.get("expected_intent", "fallback"))
            text = sample.get("text")
            case = ErrorCase(index, expected, prediction.name, prediction.confidence, text, "intent_mismatch", dict(sample.get("metadata", {})))
            if prediction.name != expected:
                errors.append(case); pairs[f"{expected}->{prediction.name}"] += 1; per_intent[expected] += 1
            if prediction.confidence < self.low_confidence_threshold:
                low_confidence.append(case)
        return ErrorAnalysisReport(len(samples), errors, dict(pairs), low_confidence, dict(per_intent))


@dataclass(frozen=True)
class RetrainingPlan:
    source_model_version: str
    source_dataset_version: str
    required_actions: tuple[str, ...]
    selected_error_indices: tuple[int, ...]
    target_intents: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]: return self.__dict__.copy()


class RetrainingPlanner:
    def plan(self, *, model_version: str, dataset_version: str, report: ErrorAnalysisReport, min_errors: int = 1) -> RetrainingPlan | None:
        if len(report.errors) < min_errors and not report.low_confidence_cases:
            return None
        actions = ["add_corrected_examples", "revalidate_entities", "resplit_dataset_without_leakage"]
        if report.confusion_pairs:
            actions.append("review_confusion_pairs")
        if report.low_confidence_cases:
            actions.append("review_low_confidence_examples")
        indices = tuple(sorted({case.index for case in report.errors + report.low_confidence_cases}))
        intents = tuple(sorted(set(report.per_intent_errors)))
        return RetrainingPlan(model_version, dataset_version, tuple(actions), indices, intents, "evaluation_error_analysis")
