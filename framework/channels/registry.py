from collections.abc import Callable
from framework.core.interfaces import ChannelAdapter

class ChannelRegistry:
    def __init__(self): self._factories: dict[str, Callable[..., ChannelAdapter]] = {}
    def register(self, channel: str, factory: Callable[..., ChannelAdapter]) -> None:
        if channel in self._factories: raise ValueError(f"Channel already registered: {channel}")
        self._factories[channel] = factory
    def create(self, channel: str, **kwargs) -> ChannelAdapter:
        factory = self._factories.get(channel)
        if not factory: raise KeyError(f"Unknown channel: {channel}")
        return factory(**kwargs)
    def names(self) -> tuple[str, ...]: return tuple(sorted(self._factories))
