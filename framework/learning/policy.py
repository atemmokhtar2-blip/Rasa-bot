from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class FeedbackType(str, Enum):
    THUMB_UP = "thumb_up"
    THUMB_DOWN = "thumb_down"
    CORRECTION = "correction"
    EXPLICIT_INTENT = "explicit_intent"
    HUMAN_REVIEW = "human_review"


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    project_id: str
    interaction_id: str
    feedback_type: FeedbackType
    intent: str | None = None
    entities: tuple[dict[str, Any], ...] = ()
    source: str = "user"
    trusted: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackService:
    def __init__(self): self.records: dict[str, FeedbackRecord] = {}
    def record(self, *, project_id: str, interaction_id: str, feedback_type: FeedbackType, intent: str | None = None, entities: tuple[dict[str, Any], ...] = (), source: str = "user", trusted: bool = False) -> FeedbackRecord:
        if feedback_type in {FeedbackType.CORRECTION, FeedbackType.EXPLICIT_INTENT} and not intent: raise ValueError("intent is required for correction feedback")
        item = FeedbackRecord(str(uuid4()), project_id, interaction_id, feedback_type, intent, entities, source, trusted)
        self.records[item.feedback_id] = item; return item
    def list_project(self, project_id: str) -> list[FeedbackRecord]: return [item for item in self.records.values() if item.project_id == project_id]


@dataclass(frozen=True)
class DatasetPromotionPolicy:
    minimum_quality: float = 80.0
    minimum_review_rate: float = 0.8
    maximum_duplicate_rate: float = 0.1
    require_human_verified: bool = True

    def evaluate(self, *, quality_score: float, review_rate: float, duplicate_rate: float, verified_count: int, total_count: int) -> tuple[bool, list[str]]:
        failures = []
        if quality_score < self.minimum_quality: failures.append("quality_below_minimum")
        if review_rate < self.minimum_review_rate: failures.append("review_rate_below_minimum")
        if duplicate_rate > self.maximum_duplicate_rate: failures.append("duplicate_rate_above_maximum")
        if self.require_human_verified and (verified_count <= 0 or verified_count < total_count * self.minimum_review_rate): failures.append("human_verification_required")
        return not failures, failures


@dataclass(frozen=True)
class PromotionDecision:
    recommendation: str
    passed: bool
    failures: tuple[str, ...]
    human_approval_required: bool = True


class ProductionPromotionPolicy:
    def decide(self, *, quality_passed: bool, regression_passed: bool, human_approved: bool = False, auto_deploy: bool = False, failures: list[str] | None = None) -> PromotionDecision:
        reasons = list(failures or [])
        if not quality_passed: reasons.append("quality_gate_failed")
        if not regression_passed: reasons.append("regression_detected")
        if not human_approved: reasons.append("human_approval_required")
        passed = quality_passed and regression_passed and (human_approved or auto_deploy)
        return PromotionDecision("PROMOTE" if passed else "REJECT" if "regression_detected" in reasons else "HOLD", passed, tuple(dict.fromkeys(reasons)), not auto_deploy)


class ContinuousTrainingOrchestrator:
    def __init__(self, *, minimum_approved_examples: int = 500, error_threshold: int = 50, cooldown_fingerprint: str | None = None):
        self.minimum_approved_examples = minimum_approved_examples; self.error_threshold = error_threshold; self.last_dataset_fingerprint = cooldown_fingerprint
    def should_trigger(self, *, trigger: str, approved_count: int, error_count: int, dataset_fingerprint: str, scheduled: bool = False) -> tuple[bool, str]:
        if dataset_fingerprint == self.last_dataset_fingerprint: return False, "dataset_unchanged"
        if trigger == "manual": self.last_dataset_fingerprint = dataset_fingerprint; return True, "manual"
        if trigger == "data_threshold" and approved_count >= self.minimum_approved_examples: self.last_dataset_fingerprint = dataset_fingerprint; return True, "approved_data_threshold"
        if trigger == "error_threshold" and error_count >= self.error_threshold: self.last_dataset_fingerprint = dataset_fingerprint; return True, "error_threshold"
        if trigger == "scheduled" and scheduled: self.last_dataset_fingerprint = dataset_fingerprint; return True, "scheduled"
        return False, "trigger_conditions_not_met"
