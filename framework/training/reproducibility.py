from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ReproducibilityManifest:
    dataset_version: str
    dataset_checksum: str
    training_config: dict[str, Any]
    model_version: str
    framework_version: str
    training_timestamp: str
    random_seed: int | None
    language: str
    environment: dict[str, str]
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    evaluation_results: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""

    @classmethod
    def build(cls, *, dataset_version: str, dataset_checksum: str, training_config: dict[str, Any], model_version: str, framework_version: str = "unknown", random_seed: int | None = 42, language: str = "ar", environment: dict[str, str] | None = None, hyperparameters: dict[str, Any] | None = None, evaluation_results: dict[str, Any] | None = None, training_timestamp: str | None = None) -> "ReproducibilityManifest":
        env = environment or {"python": sys.version.split()[0], "platform": platform.platform()}
        timestamp = training_timestamp or datetime.now(timezone.utc).isoformat()
        body = {"dataset_version": dataset_version, "dataset_checksum": dataset_checksum, "training_config": training_config, "model_version": model_version, "framework_version": framework_version, "training_timestamp": timestamp, "random_seed": random_seed, "language": language, "environment": env, "hyperparameters": hyperparameters or {}, "evaluation_results": evaluation_results or {}}
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        return cls(**body, fingerprint=fingerprint)

    def to_dict(self) -> dict[str, Any]:
        return {"dataset_version": self.dataset_version, "dataset_checksum": self.dataset_checksum, "training_config": self.training_config, "model_version": self.model_version, "framework_version": self.framework_version, "training_timestamp": self.training_timestamp, "random_seed": self.random_seed, "language": self.language, "environment": self.environment, "hyperparameters": self.hyperparameters, "evaluation_results": self.evaluation_results, "fingerprint": self.fingerprint}


def reproducibility_fingerprint(manifest: ReproducibilityManifest) -> str:
    """Return the persisted fingerprint; callers can compare manifests exactly."""
    return manifest.fingerprint
