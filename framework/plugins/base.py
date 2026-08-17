from dataclasses import dataclass, field
from typing import Any
from framework.core.registries import ActionRegistry, ToolRegistry
from framework.core.events import EventBus

@dataclass(slots=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    author: str
    description: str = ""
    permissions: set[str] = field(default_factory=set)
    dependencies: dict[str, str] = field(default_factory=dict)
    framework_min_version: str | None = None
    framework_max_version: str | None = None
    configuration_schema: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class PluginContext:
    logger: Any
    config: dict[str, Any]
    actions: ActionRegistry
    tools: ToolRegistry
    event_bus: EventBus
    permissions: set[str] = field(default_factory=set)
    services: dict[str, Any] = field(default_factory=dict)
    def require(self, permission: str) -> None:
        if permission not in self.permissions and "*" not in self.permissions: raise PermissionError(permission)

class Plugin:
    manifest: PluginManifest
    async def initialize(self, context: dict[str, Any]) -> None: raise NotImplementedError
    async def register(self, actions: ActionRegistry, tools: ToolRegistry) -> None: raise NotImplementedError
    async def shutdown(self) -> None: raise NotImplementedError
