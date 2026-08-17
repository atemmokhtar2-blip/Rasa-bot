from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


class SecretDetection:
    PATTERNS = (
        re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"(?i)\b(?:api[_ -]?key|password|secret|token)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+"),
    )
    def find(self, text: str) -> list[str]:
        return [match.group(0) for pattern in self.PATTERNS for match in pattern.finditer(text or "")]
    def contains(self, text: str) -> bool: return bool(self.find(text))


class PIIDetector:
    PATTERNS = {
        "email": re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b"),
        "phone": re.compile(r"(?<!\w)(?:\+?\d[\d\s-]{7,}\d)(?!\w)"),
    }
    def find(self, text: str) -> list[dict[str, Any]]:
        return [{"type": kind, "value": match.group(0), "start": match.start(), "end": match.end()} for kind, pattern in self.PATTERNS.items() for match in pattern.finditer(text or "")]


class PIIRedactor:
    def __init__(self, detector: PIIDetector | None = None): self.detector = detector or PIIDetector()
    def redact(self, text: str) -> str:
        result = text
        for item in sorted(self.detector.find(text), key=lambda value: value["start"], reverse=True): result = result[:item["start"]] + f"[{item['type'].upper()}_REDACTED]" + result[item["end"]:]
        return result


@dataclass(frozen=True)
class RetentionPolicy:
    retention_days: int = 30
    delete_raw_after_promotion: bool = False
    def expired(self, created_at: datetime, *, now: datetime | None = None) -> bool: return created_at + timedelta(days=self.retention_days) < (now or datetime.now(timezone.utc))


class TrainingDataFirewall:
    def __init__(self, *, secrets: SecretDetection | None = None, pii: PIIDetector | None = None, redactor: PIIRedactor | None = None): self.secrets = secrets or SecretDetection(); self.pii = pii or PIIDetector(); self.redactor = redactor or PIIRedactor(self.pii)
    def sanitize(self, *, text: str, entities: list[dict[str, Any]] | None = None, source: str = "runtime_candidate", allow_pii_redaction: bool = True) -> dict[str, Any]:
        if self.secrets.contains(text): raise ValueError("TRAINING_DATA_SECRET_DETECTED")
        findings = self.pii.find(text)
        sanitized = self.redactor.redact(text) if findings and allow_pii_redaction else text
        if findings and not allow_pii_redaction: raise ValueError("TRAINING_DATA_PII_REQUIRES_REDACTION")
        return {"text": sanitized, "entities": list(entities or []), "source": source, "trust_level": "unverified", "verification_status": "pending_review", "pii_redacted": bool(findings)}
    def assert_approved(self, *, sample_status: str, review_status: str, sanitized: bool) -> None:
        if sample_status != "approved" or review_status not in {"approved", "human_verified"} or not sanitized: raise ValueError("TRAINING_DATA_FIREWALL_BLOCKED")
