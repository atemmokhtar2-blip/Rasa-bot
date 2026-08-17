from __future__ import annotations
import logging
from typing import Any
from framework.core.registries import ActionRegistry, ToolRegistry, ProviderRegistry, PolicyRegistry, PluginRegistry
from framework.core.events import EventBus
from framework.extensions.context import ExtensionContext, ScopedConfig, ScopedEvents, ScopedStorage, SecretFacade, TaskManager, ResourceRegistry, NetworkFacade
from framework.extensions.observability import ExtensionLogger
from framework.plugins.loader import PluginLoader, LoadedPlugin
from framework.errors import PluginError
from framework.observability.audit import AuditEvent

class MemoryStorage:
    def __init__(self): self.values = {}
    async def get(self, key): return self.values.get(key)
    async def set(self, key, value): self.values[key] = value
    async def delete(self, key): self.values.pop(key, None)
    async def list(self, prefix=""): return [key for key in self.values if key.startswith(prefix)]

class ExtensionManager:
    def __init__(self, *, loader: PluginLoader, actions: ActionRegistry, tools: ToolRegistry, providers: ProviderRegistry, policies: PolicyRegistry, event_bus: EventBus, secrets: Any, plugin_registry: PluginRegistry | None = None, storage: Any = None, logger: Any = None, audit: Any = None):
        self.loader, self.actions, self.tools, self.providers, self.policies, self.event_bus, self.plugin_registry = loader, actions, tools, providers, policies, event_bus, plugin_registry or PluginRegistry()
        self.audit = audit
        self.secrets, self.storage, self.logger = secrets, storage or MemoryStorage(), logger or logging.getLogger("framework.extensions")
        self._contexts: dict[str, ExtensionContext] = {}
        self._registrations: dict[str, list[tuple[Any, Any]]] = {}
    def _context(self, manifest, configuration, *, project_id=None, environment="development") -> ExtensionContext:
        permissions = set(manifest.permissions)
        config = ScopedConfig(configuration, manifest.configuration_schema)
        resources = ResourceRegistry()
        context = ExtensionContext(plugin_id=manifest.plugin_id, project_id=project_id, environment=environment, permissions=permissions, logger=ExtensionLogger(self.logger, extension=manifest.plugin_id, project_id=project_id), config=config, events=ScopedEvents(self.event_bus, project_id or "", permissions), tasks=TaskManager(), storage=ScopedStorage(self.storage, project_id, permissions) if project_id else None, secrets=SecretFacade(self.secrets, permissions), registry={"actions": self.actions, "tools": self.tools, "providers": self.providers, "policies": self.policies}, metadata={"trust_level": manifest.trust_level, "extension_api_version": manifest.extension_api_version}, resources=resources, network=NetworkFacade(permissions, resources))
        config.validate(); return context
    async def _audit(self, event_name: str, manifest, project_id: str | None = None, **changes):
        if self.audit: await self.audit.record(AuditEvent(event_name, project_id=project_id, changes={"plugin_id": manifest.plugin_id, "version": manifest.version, **changes}))
    async def load(self, module_name: str, configuration: dict[str, Any] | None = None, *, project_id: str | None = None, environment: str = "development") -> LoadedPlugin:
        module, manifest = self.loader.discover(module_name); context = self._context(manifest, configuration or {}, project_id=project_id, environment=environment)
        record = await self.loader.load(module_name, configuration, context=context)
        try:
            self.plugin_registry.register(manifest)
            actions = getattr(module, "ACTIONS", [])
            tools = getattr(module, "TOOLS", [])
            providers = getattr(module, "PROVIDERS", [])
            policies = getattr(module, "POLICIES", [])
            registered = []
            for item in actions: self.actions.register(item); registered.append((self.actions, item))
            for item in tools: self.tools.register(item); registered.append((self.tools, item))
            for item in providers: self.providers.register(item); registered.append((self.providers, item))
            for item in policies: self.policies.register(item); registered.append((self.policies, item))
            self._registrations[manifest.plugin_id] = registered
            plugin = getattr(module, "PLUGIN", None)
            if plugin is not None and hasattr(plugin, "register"):
                result = plugin.register(self.actions, self.tools)
                if hasattr(result, "__await__"): await result
            self._contexts[manifest.plugin_id] = context; record.context = context
            await self._audit("EXTENSION_ENABLED", manifest, project_id, actions=[getattr(x, "name", None) for x in actions], tools=[getattr(x, "name", None) for x in tools], providers=[getattr(x, "name", None) for x in providers])
            return record
        except Exception as exc:
            for registry, item in self._registrations.pop(manifest.plugin_id, []): registry.unregister(getattr(item, "name", None) or getattr(item, "plugin_id", None), getattr(item, "version", "1.0.0"))
            await self.loader.unload(manifest.name)
            raise PluginError(f"Plugin activation rolled back: {manifest.name}") from exc
    async def unload(self, plugin_id: str) -> None:
        context = self._contexts.get(plugin_id)
        if context:
            context.events.unsubscribe_all(); await context.tasks.cancel_all()
            if context.resources.count(): raise PluginError(f"Plugin {plugin_id} has active resources", details={"resources": sorted(context.resources.active())})
            self._contexts.pop(plugin_id, None)
        record = self.loader.loaded.get(plugin_id)
        for registry, item in self._registrations.pop(plugin_id, []): registry.unregister(getattr(item, "name", None) or getattr(item, "plugin_id", None), getattr(item, "version", "1.0.0"))
        if record: self.plugin_registry.unregister(record.manifest.name, version=record.manifest.version)
        await self.loader.unload(plugin_id)
    async def disable(self, plugin_id: str) -> None:
        record = self.loader.loaded.get(plugin_id); await self.loader.disable(plugin_id)
        if record: await self._audit("EXTENSION_DISABLED", record.manifest, record.context.project_id if record.context else None)
    def health(self) -> list[dict[str, Any]]: return self.loader.health()
