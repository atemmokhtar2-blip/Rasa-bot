from __future__ import annotations
import logging
import time
from typing import Any
from framework.security.redaction import SensitiveDataRedactor

class SecretRedactor(SensitiveDataRedactor):
    pass

class ExtensionLogger:
    def __init__(self, logger: logging.Logger, *, extension: str, project_id: str | None = None, request_id: str | None = None, trace_id: str | None = None): self.logger, self.extension, self.project_id, self.request_id, self.trace_id = logger, extension, project_id, request_id, trace_id
    def _extra(self, extra: dict[str, Any] | None = None):
        values = {"extension": self.extension, "project_id": self.project_id, "request_id": self.request_id, "trace_id": self.trace_id}; values.update(extra or {}); return SecretRedactor().redact(values)
    def info(self, event: str, *, extra: dict[str, Any] | None = None): self.logger.info(event, extra=self._extra(extra))
    def warning(self, event: str, *, extra: dict[str, Any] | None = None): self.logger.warning(event, extra=self._extra(extra))
    def error(self, event: str, *, extra: dict[str, Any] | None = None): self.logger.error(event, extra=self._extra(extra))
    def timed(self, action: str): return _TimedExtensionLog(self, action)

class _TimedExtensionLog:
    def __init__(self, logger: ExtensionLogger, action: str): self.logger, self.action, self.started = logger, action, time.perf_counter()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.logger.info("extension_action", extra={"action": self.action, "duration_ms": (time.perf_counter() - self.started) * 1000, "status": "error" if exc else "success"})
