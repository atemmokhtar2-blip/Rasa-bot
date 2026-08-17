from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ThresholdCandidate:
    accept_threshold: float
    clarification_threshold: float
    fallback_threshold: float
    objective: float
    accepted: int
    clarified: int
    fallback: int
    correct_accepted: int
    incorrect_accepted: int
    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

@dataclass(frozen=True)
class ThresholdOptimizationResult:
    accept_threshold: float
    clarification_threshold: float
    fallback_threshold: float
    objective: float
    samples: int
    candidates: tuple[ThresholdCandidate, ...] = field(default_factory=tuple)
    def to_dict(self) -> dict[str, Any]:
        return {"accept_threshold": self.accept_threshold, "clarification_threshold": self.clarification_threshold, "fallback_threshold": self.fallback_threshold, "objective": self.objective, "samples": self.samples, "candidates": [candidate.to_dict() for candidate in self.candidates]}

class ThresholdOptimizer:
    """Selects confidence thresholds from labeled evaluation predictions.

    The optimizer uses only observed confidence/correctness pairs. It never invents
    labels or predictions and returns a deterministic result for a fixed grid.
    """
    def __init__(self, *, step: float = 0.05, minimum_accept: float = 0.5, minimum_clarification: float = 0.2):
        if not 0 < step <= 1 or not 0 <= minimum_clarification <= minimum_accept <= 1:
            raise ValueError("invalid threshold optimizer configuration")
        self.step, self.minimum_accept, self.minimum_clarification = step, minimum_accept, minimum_clarification

    def optimize(self, samples: list[dict[str, Any]]) -> ThresholdOptimizationResult:
        if not samples: raise ValueError("Threshold optimization data cannot be empty")
        observations = [(float(sample["prediction"].confidence), sample["prediction"].name == str(sample.get("expected_intent", "fallback"))) for sample in samples]
        grid = [round(index * self.step, 10) for index in range(round(1 / self.step) + 1)]
        candidates: list[ThresholdCandidate] = []
        for fallback in (value for value in grid if value <= self.minimum_clarification):
            for clarification in (value for value in grid if value >= max(self.minimum_clarification, fallback) and value <= self.minimum_accept):
                for accept in (value for value in grid if value >= max(self.minimum_accept, clarification)):
                    accepted = clarified = fallback_count = correct_accepted = incorrect_accepted = 0; objective = 0.0
                    for confidence, correct in observations:
                        if confidence >= accept:
                            accepted += 1; correct_accepted += int(correct); incorrect_accepted += int(not correct); objective += 1.0 if correct else -1.0
                        elif confidence >= clarification:
                            clarified += 1; objective += 0.2 if correct else -0.1
                        else:
                            fallback_count += 1; objective += 0.1 if not correct else -0.05
                    candidates.append(ThresholdCandidate(accept, clarification, fallback, objective, accepted, clarified, fallback_count, correct_accepted, incorrect_accepted))
        best = max(candidates, key=lambda candidate: (candidate.objective, candidate.correct_accepted, -candidate.incorrect_accepted, -candidate.accept_threshold, -candidate.clarification_threshold))
        return ThresholdOptimizationResult(best.accept_threshold, best.clarification_threshold, best.fallback_threshold, best.objective, len(samples), tuple(sorted(candidates, key=lambda item: item.objective, reverse=True)[:10]))

    @staticmethod
    def classify(confidence: float, result: ThresholdOptimizationResult) -> str:
        if confidence >= result.accept_threshold: return "accept"
        if confidence >= result.clarification_threshold: return "clarify"
        return "fallback"

__all__ = ["ThresholdCandidate", "ThresholdOptimizationResult", "ThresholdOptimizer"]

