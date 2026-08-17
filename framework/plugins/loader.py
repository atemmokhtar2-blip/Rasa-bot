import importlib
from dataclasses import dataclass, field
from typing import Any
from framework.plugins.base import PluginManifest

@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    module: Any
    enabled: bool = True

class PluginLoader:
    def __init__(self): self.loaded: dict[str, LoadedPlugin] = {}
    def load(self, module_name: str, configuration: dict[str, Any] | None = None) -> LoadedPlugin:
        module = importlib.import_module(module_name)
        manifest_data = getattr(module, "PLUGIN_MANIFEST", None)
        if not isinstance(manifest_data, PluginManifest): raise ValueError(f"{module_name} must export PLUGIN_MANIFEST")
        for dependency in manifest_data.dependencies:
            if dependency not in self.loaded: raise RuntimeError(f"Plugin dependency is not loaded: {dependency}")
        plugin = LoadedPlugin(manifest_data, module)
        initializer = getattr(module, "initialize", None)
        if initializer: initializer(configuration or {})
        self.loaded[manifest_data.name] = plugin
        return plugin
    def unload(self, name: str) -> None:
        plugin = self.loaded.pop(name, None)
        if plugin:
            shutdown = getattr(plugin.module, "shutdown", None)
            if shutdown: shutdown()
    def list(self) -> list[LoadedPlugin]: return list(self.loaded.values())
