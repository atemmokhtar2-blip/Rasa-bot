import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Iterable
from framework.plugins.base import PluginManifest

@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    module: Any
    enabled: bool = True

class PluginLoader:
    def __init__(self): self.loaded: dict[str, LoadedPlugin] = {}

    def _manifest(self, module_name: str) -> tuple[Any, PluginManifest]:
        module = importlib.import_module(module_name)
        manifest = getattr(module, "PLUGIN_MANIFEST", None)
        if not isinstance(manifest, PluginManifest): raise ValueError(f"{module_name} must export PLUGIN_MANIFEST")
        return module, manifest

    async def load(self, module_name: str, configuration: dict[str, Any] | None = None) -> LoadedPlugin:
        module, manifest = self._manifest(module_name)
        missing = [dependency for dependency in manifest.dependencies if dependency not in self.loaded]
        if missing: raise RuntimeError(f"Plugin dependencies are not loaded: {', '.join(missing)}")
        if manifest.name in self.loaded: raise RuntimeError(f"Plugin already loaded: {manifest.name}")
        initializer = getattr(module, "initialize", None)
        if initializer:
            result = initializer(configuration or {})
            if inspect.isawaitable(result): await result
        plugin = LoadedPlugin(manifest, module)
        self.loaded[manifest.name] = plugin
        return plugin

    async def load_many(self, module_names: Iterable[str], configuration: dict[str, Any] | None = None) -> list[LoadedPlugin]:
        pending = {name: self._manifest(name) for name in module_names}
        loaded: list[LoadedPlugin] = []
        pending_names = {manifest.name for _, manifest in pending.values()}
        while pending:
            progress = False
            for module_name, (_, manifest) in list(pending.items()):
                unavailable = [dependency for dependency in manifest.dependencies if dependency not in self.loaded and dependency not in pending_names]
                if unavailable: raise RuntimeError(f"Plugin dependency is unavailable: {manifest.name}: {', '.join(unavailable)}")
                if all(dependency in self.loaded for dependency in manifest.dependencies):
                    pending.pop(module_name)
                    pending_names.discard(manifest.name)
                    loaded.append(await self.load(module_name, configuration))
                    progress = True
            if not progress: raise RuntimeError("Plugin dependency cycle detected")
        return loaded

    async def unload(self, name: str) -> None:
        dependents = [plugin.manifest.name for plugin in self.loaded.values() if name in plugin.manifest.dependencies]
        if dependents: raise RuntimeError(f"Cannot unload {name}; dependents are loaded: {', '.join(dependents)}")
        plugin = self.loaded.pop(name, None)
        if plugin:
            shutdown = getattr(plugin.module, "shutdown", None)
            if shutdown:
                result = shutdown()
                if inspect.isawaitable(result): await result

    def list(self) -> list[LoadedPlugin]: return list(self.loaded.values())
