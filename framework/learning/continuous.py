from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import uuid4


class CandidateStatus(str, Enum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class SampleStatus(str, Enum):
    COLLECTED = "collected"
    FILTERED = "filtered"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROMOTED = "promoted"


@dataclass(frozen=True)
class InteractionRecord:
    interaction_id: str
    project_id: str
    session_id: str | None
    timestamp: datetime
    language: str
    input_text: str
    predicted_intent: str | None
    confidence: float | None
    entities: tuple[dict[str, Any], ...]
    response: str | None
    model_version: str | None
    processing_time_ms: float | None
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"interaction_id": self.interaction_id, "project_id": self.project_id, "session_id": self.session_id, "timestamp": self.timestamp.isoformat(), "language": self.language, "input": self.input_text, "predicted_intent": self.predicted_intent, "confidence": self.confidence, "entities": list(self.entities), "response": self.response, "model_version": self.model_version, "processing_time": self.processing_time_ms, "status": self.status, "metadata": self.metadata}


@dataclass(frozen=True)
class CandidateSample:
    sample_id: str
    project_id: str
    interaction_id: str
    text: str
    suggested_intent: str | None
    entities: tuple[dict[str, Any], ...]
    language: str
    context: dict[str, Any]
    quality_score: float
    status: CandidateStatus = CandidateStatus.PENDING
    sample_status: SampleStatus = SampleStatus.PENDING_REVIEW
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


class PrivacyRedactor:
    """Redacts common credentials before telemetry is persisted."""

    SECRET_PATTERNS = (
        re.compile(r"(?i)(bot\s*token|api[_ -]?key|secret|password)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+"),
    )

    def text(self, value: str | None) -> str | None:
        if value is None:
            return None
        result = value
        for pattern in self.SECRET_PATTERNS:
            result = pattern.sub("[REDACTED]", result)
        return result

    def mapping(self, value: dict[str, Any] | None) -> dict[str, Any]:
        if not value:
            return {}
        blocked = {"token", "bot_token", "api_key", "secret", "password", "authorization"}
        return {key: "[REDACTED]" if key.lower() in blocked else self.text(item) if isinstance(item, str) else item for key, item in value.items()}


class InteractionCollectionService:
    def __init__(self, *, redactor: PrivacyRedactor | None = None, low_confidence_threshold: float = 0.55, high_confidence_error_threshold: float = 0.9):
        self.redactor = redactor or PrivacyRedactor()
        self.low_confidence_threshold = low_confidence_threshold
        self.high_confidence_error_threshold = high_confidence_error_threshold
        self.interactions: dict[str, InteractionRecord] = {}
        self.candidates: dict[str, CandidateSample] = {}
        self._fingerprints: dict[tuple[str, str], str] = {}

    def collect(self, *, project_id: str, session_id: str | None, language: str, input_text: str, predicted_intent: str | None, confidence: float | None, entities: Iterable[dict[str, Any]] = (), response: str | None = None, model_version: str | None = None, processing_time_ms: float | None = None, status: str = "completed", metadata: dict[str, Any] | None = None) -> InteractionRecord:
        if not project_id:
            raise ValueError("project_id is required")
        record = InteractionRecord(str(uuid4()), project_id, session_id, datetime.now(timezone.utc), language, self.redactor.text(input_text) or "", predicted_intent, confidence, tuple(self.redactor.mapping(dict(entity)) for entity in entities), self.redactor.text(response), model_version, processing_time_ms, status, self.redactor.mapping(metadata))
        self.interactions[record.interaction_id] = record
        return record

    def candidate_from_interaction(self, interaction_id: str, *, project_id: str, suggested_intent: str | None = None, context: dict[str, Any] | None = None, quality_score: float | None = None) -> CandidateSample:
        interaction = self.interactions.get(interaction_id)
        if interaction is None or interaction.project_id != project_id:
            raise KeyError("Interaction not found")
        fingerprint = hashlib.sha256(f"{interaction.input_text}\0{suggested_intent or interaction.predicted_intent or ''}".encode()).hexdigest()
        if (project_id, fingerprint) in self._fingerprints:
            return replace(self.candidates[self._fingerprints[(project_id, fingerprint)]], status=CandidateStatus.DUPLICATE, sample_status=SampleStatus.REJECTED)
        score = quality_score if quality_score is not None else self._quality_score(interaction)
        candidate = CandidateSample(str(uuid4()), project_id, interaction_id, interaction.input_text, suggested_intent or interaction.predicted_intent, interaction.entities, interaction.language, self.redactor.mapping(context), max(0.0, min(100.0, score)))
        self.candidates[candidate.sample_id] = candidate; self._fingerprints[(project_id, fingerprint)] = candidate.sample_id
        return candidate

    def transition_candidate(self, sample_id: str, *, project_id: str, status: CandidateStatus, sample_status: SampleStatus) -> CandidateSample:
        candidate = self.candidates.get(sample_id)
        if candidate is None or candidate.project_id != project_id:
            raise KeyError("Candidate sample not found")
        if sample_status == SampleStatus.PROMOTED and status != CandidateStatus.APPROVED:
            raise ValueError("Only approved candidates can be promoted")
        self.candidates[sample_id] = replace(candidate, status=status, sample_status=sample_status)
        return self.candidates[sample_id]

    def list_candidates(self, project_id: str, *, status: CandidateStatus | None = None, sample_status: SampleStatus | None = None) -> list[CandidateSample]:
        return [item for item in self.candidates.values() if item.project_id == project_id and (status is None or item.status == status) and (sample_status is None or item.sample_status == sample_status)]

    def low_confidence(self, project_id: str) -> list[InteractionRecord]:
        return [item for item in self.interactions.values() if item.project_id == project_id and item.confidence is not None and item.confidence < self.low_confidence_threshold]

    def high_confidence_errors(self, project_id: str, *, known_correct_intents: dict[str, str] | None = None) -> list[InteractionRecord]:
        known_correct_intents = known_correct_intents or {}
        return [item for item in self.interactions.values() if item.project_id == project_id and item.confidence is not None and item.confidence >= self.high_confidence_error_threshold and known_correct_intents.get(item.interaction_id) is not None and known_correct_intents[item.interaction_id] != item.predicted_intent]

    @staticmethod
    def _quality_score(interaction: InteractionRecord) -> float:
        score = 50.0
        if interaction.input_text.strip(): score += 20
        if interaction.predicted_intent: score += 10
        if interaction.confidence is not None: score += min(15.0, interaction.confidence * 15)
        if interaction.status == "completed": score += 5
        return round(min(100.0, score), 2)
