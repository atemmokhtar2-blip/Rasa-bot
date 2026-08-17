from dataclasses import dataclass, field
from typing import Any
from framework.core.registries import ActionRegistry, ToolRegistry
from framework.core.events import EventBus
from framework.extensions.context import ExtensionContext

@dataclass(slots=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    author: str
    description: str = ""
    framework_version: str | None = None
    extension_api_version: str = "1"
    entrypoint: str | None = None
    signature: str | None = None
    checksum: str | None = None
    permissions: set[str] = field(default_factory=set)
    dependencies: dict[str, str] = field(default_factory=dict)
    framework_min_version: str | None = None
    framework_max_version: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)
    configuration_schema: dict[str, Any] = field(default_factory=dict)
    scope: str = "global"
    trust_level: str = "developer"
    experimental: bool = False
    status: str = "discovered"
    def __post_init__(self):
        if self.framework_version and not self.framework_min_version: self.framework_min_version = self.framework_version

@dataclass(slots=True)
class PluginContext:
    logger: Any
    config: dict[str, Any]
    actions: ActionRegistry
    tools: ToolRegistry
    event_bus: EventBus
    permissions: set[str] = field(default_factory=set)
    services: dict[str, Any] = field(default_factory=dict)
    extension: ExtensionContext | None = None
    def require(self, permission: str) -> None:
        if permission not in self.permissions and "*" not in self.permissions: raise PermissionError(permission)
    def as_extension_context(self) -> ExtensionContext:
        if self.extension is None: raise RuntimeError("ExtensionContext is not initialized")
        return self.extension

class Plugin:
    manifest: PluginManifest
    async def initialize(self, context: Any) -> None: raise NotImplementedError
    async def register(self, actions: ActionRegistry, tools: ToolRegistry) -> None: raise NotImplementedError
    async def shutdown(self) -> None: raise NotImplementedError
    async def health(self) -> dict[str, Any]: return {"status": "ready", "version": self.manifest.version if hasattr(self, "manifest") else None, "details": {}}
