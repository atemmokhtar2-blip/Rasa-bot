from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    CORRECT = "correct"
    CONFLICT = "review_conflict"


@dataclass(frozen=True)
class AnnotationVersion:
    annotation_id: str
    sample_id: str
    version: int
    reviewer_id: str
    intent: str | None
    entities: tuple[dict[str, Any], ...]
    context: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    parent_version: int | None = None


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    project_id: str
    sample_id: str
    reviewer_id: str
    decision: ReviewDecision
    corrected_intent: str | None
    corrected_entities: tuple[dict[str, Any], ...]
    notes: str
    annotation_version: int | None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ReviewConflict:
    conflict_id: str
    project_id: str
    sample_id: str
    review_ids: tuple[str, ...]
    competing_intents: tuple[str, ...]
    status: str = "open"
    resolution: str | None = None


class ConflictResolver:
    def resolve(self, conflict: ReviewConflict, *, resolver_id: str, intent: str, policy: str = "senior_reviewer") -> ReviewConflict:
        if policy not in {"senior_reviewer", "consensus", "rule"}:
            raise ValueError("Unsupported conflict resolution policy")
        if intent not in conflict.competing_intents:
            raise ValueError("Resolution must select one of the competing intents")
        return ReviewConflict(conflict.conflict_id, conflict.project_id, conflict.sample_id, conflict.review_ids, conflict.competing_intents, "resolved", f"{policy}:{resolver_id}:{intent}")


class HumanReviewService:
    def __init__(self):
        self.reviews: dict[str, ReviewRecord] = {}
        self.annotations: dict[str, list[AnnotationVersion]] = {}
        self.conflicts: dict[str, ReviewConflict] = {}

    def review(self, *, project_id: str, sample_id: str, reviewer_id: str, decision: ReviewDecision, corrected_intent: str | None = None, corrected_entities: tuple[dict[str, Any], ...] = (), notes: str = "", context: dict[str, Any] | None = None) -> ReviewRecord:
        if decision == ReviewDecision.CORRECT and not corrected_intent:
            raise ValueError("Corrected intent is required for correction reviews")
        previous = self.annotations.get(sample_id, [])
        version = None
        if decision in {ReviewDecision.APPROVE, ReviewDecision.CORRECT}:
            version = len(previous) + 1
            annotation = AnnotationVersion(str(uuid4()), sample_id, version, reviewer_id, corrected_intent, corrected_entities, context or {}, parent_version=previous[-1].version if previous else None)
            self.annotations[sample_id] = [*previous, annotation]
        record = ReviewRecord(str(uuid4()), project_id, sample_id, reviewer_id, decision, corrected_intent, corrected_entities, notes, version)
        self.reviews[record.review_id] = record
        self._detect_conflict(record)
        return record

    def _detect_conflict(self, record: ReviewRecord) -> None:
        relevant = [item for item in self.reviews.values() if item.project_id == record.project_id and item.sample_id == record.sample_id and item.corrected_intent]
        intents = tuple(sorted({item.corrected_intent for item in relevant if item.corrected_intent}))
        if len(intents) > 1:
            conflict = ReviewConflict(str(uuid4()), record.project_id, record.sample_id, tuple(item.review_id for item in relevant), intents)
            self.conflicts[conflict.conflict_id] = conflict
            for item in relevant:
                self.reviews[item.review_id] = ReviewRecord(item.review_id, item.project_id, item.sample_id, item.reviewer_id, ReviewDecision.CONFLICT, item.corrected_intent, item.corrected_entities, item.notes, item.annotation_version, item.created_at)

    def list_conflicts(self, project_id: str) -> list[ReviewConflict]:
        return [item for item in self.conflicts.values() if item.project_id == project_id and item.status == "open"]

    def resolve(self, conflict_id: str, *, project_id: str, resolver_id: str, intent: str, policy: str = "senior_reviewer") -> ReviewConflict:
        conflict = self.conflicts.get(conflict_id)
        if conflict is None or conflict.project_id != project_id:
            raise KeyError("Review conflict not found")
        resolved = ConflictResolver().resolve(conflict, resolver_id=resolver_id, intent=intent, policy=policy)
        self.conflicts[conflict_id] = resolved
        return resolved
