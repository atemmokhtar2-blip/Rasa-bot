from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from framework.extensions.decorators import action, tool, middleware, FunctionAction, FunctionTool, FunctionMiddleware
from framework.core.middleware import MiddlewarePipeline
from framework.core.registries import ActionRegistry, ToolRegistry, ProviderRegistry, PolicyRegistry
from framework.plugins.base import PluginManifest

@dataclass
class ExtensionBuilder:
    project_id: str | None = None
    environment: str = "development"
    actions: ActionRegistry = field(default_factory=ActionRegistry)
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    providers: ProviderRegistry = field(default_factory=ProviderRegistry)
    policies: PolicyRegistry = field(default_factory=PolicyRegistry)
    middleware: MiddlewarePipeline = field(default_factory=MiddlewarePipeline)
    plugins: list[PluginManifest] = field(default_factory=list)
    def register_action(self, action_definition: Any, *, override: bool = False): self.actions.register(action_definition, override=override); return action_definition
    def register_tool(self, tool_definition: Any, *, override: bool = False): self.tools.register(tool_definition, override=override); return tool_definition
    def register_provider(self, provider: Any, *, override: bool = False): self.providers.register(provider, override=override); return provider
    def register_policy(self, policy: Any, *, override: bool = False): self.policies.register(policy, override=override); return policy
    def add_middleware(self, name: str, middleware: Any, *, priority: int = 100, security: bool = False): self.middleware.register(name, middleware, priority=priority, security=security); return middleware
    def add_plugin(self, manifest: PluginManifest): self.plugins.append(manifest); return manifest

class ExtensionsAPI:
    """Stable local SDK surface; remote installation/loading is intentionally not implicit."""
    api_version = "1"
    def __init__(self): self.builder = ExtensionBuilder()
    def action(self, name: str, **options): return action(name, scope="project" if self.builder.project_id else "global", project_id=self.builder.project_id, environment=self.builder.environment, **options)
    def tool(self, name: str, **options): return tool(name, scope="project" if self.builder.project_id else "global", project_id=self.builder.project_id, environment=self.builder.environment, **options)
    def middleware(self, name: str, **options): return middleware(name, scope="project" if self.builder.project_id else "global", project_id=self.builder.project_id, **options)
    def register(self, extension: Any, *, override: bool = False):
        if isinstance(extension, FunctionAction): return self.builder.register_action(extension, override=override)
        if isinstance(extension, FunctionTool): return self.builder.register_tool(extension, override=override)
        if isinstance(extension, FunctionMiddleware): return self.builder.add_middleware(extension.name, extension, priority=extension.priority, security=extension.security)
        if isinstance(extension, PluginManifest): return self.builder.add_plugin(extension)
        if getattr(extension, "provider_type", None): return self.builder.register_provider(extension, override=override)
        raise TypeError("Unsupported extension type")
