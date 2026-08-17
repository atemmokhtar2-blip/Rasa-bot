from dataclasses import dataclass, field
from typing import Any
from framework.core.registries import ActionRegistry, ToolRegistry

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

class Plugin:
    manifest: PluginManifest
    async def initialize(self, context: dict[str, Any]) -> None: pass
    async def register(self, actions: ActionRegistry, tools: ToolRegistry) -> None: pass
    async def shutdown(self) -> None: pass
