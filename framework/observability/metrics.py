from collections import Counter
from threading import Lock

class MetricsRegistry:
    def __init__(self): self._counters = Counter(); self._lock = Lock()
    def inc(self, name: str, value: int = 1, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock: self._counters[key] += value
    def render(self) -> str:
        lines = []
        for (name, labels), value in sorted(self._counters.items()):
            label_text = "{" + ",".join(f'{key}="{val}"' for key, val in labels) + "}" if labels else ""
            lines.append(f"{name}{label_text} {value}")
        return "\n".join(lines) + "\n"
