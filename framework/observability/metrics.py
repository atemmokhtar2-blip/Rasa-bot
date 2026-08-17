from __future__ import annotations
from collections import Counter
from contextlib import contextmanager
from threading import Lock
from time import perf_counter
from typing import Iterator

EXTENSION_METRICS = {
    "plugin_execution_count",
    "action_execution_count",
    "tool_execution_count",
    "provider_execution_count",
    "provider_latency_ms",
    "extension_errors_total",
}

class MetricsRegistry:
    def __init__(self):
        self._counters = Counter(); self._observations = Counter(); self._lock = Lock()
    def inc(self, name: str, value: int = 1, **labels: str) -> None:
        key = (name, tuple(sorted((str(k), str(v)) for k, v in labels.items())))
        with self._lock: self._counters[key] += value
    def observe(self, name: str, value: float, **labels: str) -> None:
        key = (name, tuple(sorted((str(k), str(v)) for k, v in labels.items())))
        with self._lock:
            self._observations[(key, "sum")] += value
            self._observations[(key, "count")] += 1
    @contextmanager
    def timer(self, name: str, **labels: str) -> Iterator[None]:
        started = perf_counter()
        try: yield
        finally: self.observe(name, (perf_counter() - started) * 1000, **labels)
    def extension_started(self, kind: str, name: str, **labels: str) -> None:
        metric = {"plugin": "plugin_execution_count", "action": "action_execution_count", "tool": "tool_execution_count", "provider": "provider_execution_count"}.get(kind, "extension_execution_count")
        self.inc(metric, extension=name, **labels)
    def extension_finished(self, kind: str, name: str, duration_ms: float, *, status: str = "success", **labels: str) -> None:
        self.observe(f"{kind}_latency_ms", duration_ms, extension=name, status=status, **labels)
        if status != "success": self.inc("extension_errors_total", extension=name, kind=kind, status=status, **labels)
    def render(self) -> str:
        lines = []
        with self._lock:
            counters = list(self._counters.items()); observations = list(self._observations.items())
        for (name, labels), value in sorted(counters):
            label_text = "{" + ",".join(f'{key}="{val}"' for key, val in labels) + "}" if labels else ""
            lines.append(f"{name}{label_text} {value}")
        for ((name, labels), suffix), value in sorted(observations):
            label_text = "{" + ",".join(f'{key}="{val}"' for key, val in labels) + "}" if labels else ""
            lines.append(f"{name}_{suffix}{label_text} {value}")
        return "\n".join(lines) + "\n"
