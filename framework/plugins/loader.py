from __future__ import annotations
import importlib
import inspect
from importlib import metadata
from dataclasses import dataclass, field
from typing import Any, Iterable
from packaging.specifiers import SpecifierSet
from packaging.version import Version, InvalidVersion
from framework.errors import PluginError, ValidationError
from framework.plugins.base import PluginManifest
from framework.extensions.context import ExtensionContext, TaskManager

STATUSES = {"discovered", "validated", "loaded", "initialized", "active", "unhealthy", "disabled", "unloaded"}

@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    module: Any
    enabled: bool = True
    status: str = "discovered"
    context: ExtensionContext | None = None
    tasks: TaskManager = field(default_factory=TaskManager)
    error: str | None = None
    def __post_init__(self): self.manifest.status = self.status

class PluginLoader:
    def __init__(self, *, framework_version: str = "1.0.0", extension_api_version: str = "1", context_factory=None): self.loaded: dict[str, LoadedPlugin] = {}; self.framework_version, self.extension_api_version, self.context_factory = framework_version, extension_api_version, context_factory
    def discover(self, module_name: str) -> tuple[Any, PluginManifest]:
        try: module = importlib.import_module(module_name)
        except Exception as exc: raise PluginError(f"Plugin discovery failed: {module_name}") from exc
        manifest = getattr(module, "PLUGIN_MANIFEST", None)
        if not isinstance(manifest, PluginManifest): raise ValidationError(f"{module_name} must export PLUGIN_MANIFEST")
        return module, manifest
    def _validate_manifest(self, manifest: PluginManifest, configuration: dict[str, Any]) -> None:
        if not manifest.plugin_id or not manifest.name or not manifest.version or not manifest.author: raise ValidationError("Plugin manifest is incomplete")
        if manifest.extension_api_version != self.extension_api_version: raise PluginError(f"Unsupported extension API version: {manifest.extension_api_version}")
        try: Version(manifest.version)
        except InvalidVersion as exc: raise ValidationError(f"Invalid plugin version: {manifest.version}") from exc
        if manifest.framework_min_version and Version(self.framework_version) < Version(manifest.framework_min_version): raise PluginError(f"Plugin requires framework >= {manifest.framework_min_version}")
        if manifest.framework_max_version and Version(self.framework_version) > Version(manifest.framework_max_version): raise PluginError(f"Plugin requires framework <= {manifest.framework_max_version}")
        if manifest.configuration_schema:
            for key in manifest.configuration_schema.get("required", []):
                if key not in configuration: raise ValidationError(f"Missing plugin configuration key: {key}")
            allowed = set(manifest.configuration_schema.get("properties", configuration).keys())
            unknown = set(configuration) - allowed
            if allowed and unknown: raise ValidationError(f"Unknown plugin configuration keys: {sorted(unknown)}")
        if manifest.scope not in {"global", "project", "environment", "project_environment"}: raise ValidationError("Invalid plugin scope")
    def discover_entrypoints(self, group: str = "rasa_bot.plugins") -> dict[str, str]:
        entries = metadata.entry_points()
        selected = entries.select(group=group) if hasattr(entries, "select") else entries.get(group, [])
        return {entry.name: entry.value.split(":", 1)[0] for entry in selected}
    def _manifest(self, module_name: str) -> tuple[Any, PluginManifest]: return self.discover(module_name)
    async def load(self, module_name: str, configuration: dict[str, Any] | None = None, *, context: ExtensionContext | None = None) -> LoadedPlugin:
        module, manifest = self.discover(module_name); config = dict(manifest.configuration); config.update(configuration or {})
        self._validate_manifest(manifest, config)
        if manifest.name in self.loaded or manifest.plugin_id in self.loaded: raise PluginError(f"Plugin already loaded: {manifest.name}")
        for dependency, requirement in manifest.dependencies.items():
            dependency_plugin = self.loaded.get(dependency)
            if dependency_plugin is None: raise PluginError(f"Plugin dependency is not loaded: {dependency}")
            if requirement:
                try:
                    if Version(dependency_plugin.manifest.version) not in SpecifierSet(requirement): raise PluginError(f"Dependency version conflict for {dependency}")
                except InvalidVersion as exc: raise PluginError(f"Invalid dependency version: {dependency}") from exc
        record = LoadedPlugin(manifest, module, status="validated", context=context)
        self.loaded[manifest.name] = record
        self.loaded[manifest.plugin_id] = record
        try:
            record.status = "loaded"; manifest.status = "loaded"
            initializer = getattr(module, "initialize", None)
            if initializer:
                result = initializer(context or config)
                if inspect.isawaitable(result): await result
            record.status = "initialized"; manifest.status = "initialized"
            plugin_object = getattr(module, "PLUGIN", None)
            if plugin_object is not None and hasattr(plugin_object, "initialize"):
                result = plugin_object.initialize(context or config)
                if inspect.isawaitable(result): await result
            record.status = "active"; manifest.status = "active"
            record.enabled = True
            return record
        except Exception as exc:
            record.status = "unhealthy"; manifest.status = "unhealthy"; record.enabled = False; record.error = str(exc)
            self.loaded.pop(manifest.name, None); self.loaded.pop(manifest.plugin_id, None)
            raise PluginError(f"Plugin initialization failed: {manifest.name}") from exc
    async def load_many(self, module_names: Iterable[str], configuration: dict[str, Any] | None = None) -> list[LoadedPlugin]:
        pending = {name: self.discover(name) for name in module_names}; loaded: list[LoadedPlugin] = []; pending_by_id = {manifest.plugin_id: (name, manifest) for name, (_, manifest) in pending.items()}; pending_by_name = {manifest.name: (name, manifest) for name, (_, manifest) in pending.items()}
        while pending:
            progress = False
            for module_name, (_, manifest) in list(pending.items()):
                unavailable = [dependency for dependency in manifest.dependencies if dependency not in self.loaded and dependency not in pending_by_id and dependency not in pending_by_name]
                if unavailable: raise PluginError(f"Plugin dependency is unavailable: {manifest.name}: {', '.join(unavailable)}")
                if all(dependency in self.loaded for dependency in manifest.dependencies):
                    pending.pop(module_name); pending_by_id.pop(manifest.plugin_id, None); pending_by_name.pop(manifest.name, None)
                    loaded.append(await self.load(module_name, configuration)); progress = True
            if not progress: raise PluginError("Plugin dependency cycle detected")
        return loaded
    async def disable(self, name: str) -> None:
        record = self.loaded.get(name)
        if record: record.enabled = False; record.status = "disabled"; record.manifest.status = "disabled"
    async def unload(self, name: str) -> None:
        record = self.loaded.get(name)
        if record is None: return
        canonical = record.manifest.name
        dependents = [plugin.manifest.name for key, plugin in self.loaded.items() if key == plugin.manifest.name and canonical in plugin.manifest.dependencies]
        if dependents: raise PluginError(f"Cannot unload {canonical}; dependents are loaded: {', '.join(dependents)}")
        try:
            await record.tasks.cancel_all()
            if record.context: record.context.events.unsubscribe_all()
            shutdown = getattr(record.module, "shutdown", None)
            if shutdown:
                result = shutdown()
                if inspect.isawaitable(result): await result
            plugin_object = getattr(record.module, "PLUGIN", None)
            if plugin_object is not None and hasattr(plugin_object, "shutdown"):
                result = plugin_object.shutdown()
                if inspect.isawaitable(result): await result
        finally:
            record.status = "unloaded"; record.manifest.status = "unloaded"; self.loaded.pop(record.manifest.name, None); self.loaded.pop(record.manifest.plugin_id, None)
    def list(self) -> list[LoadedPlugin]: return list({id(record): record for record in self.loaded.values()}.values())
    def health(self) -> list[dict[str, Any]]: return [{"plugin_id": item.manifest.plugin_id, "name": item.manifest.name, "version": item.manifest.version, "status": item.status, "error": item.error} for item in self.list()]
