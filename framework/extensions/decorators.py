from __future__ import annotations
import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from framework.errors import ActionError, AuthorizationError, ToolError, ValidationError

@dataclass(frozen=True)
class DeveloperActionContext:
    user: Any
    session: Any
    message: Any
    intent: Any
    entities: list[Any]
    metadata: dict[str, Any]
    project: Any
    logger: Any
    request_id: str | None = None
    trace_id: str | None = None
    tools: Any = None

@dataclass(frozen=True)
class ActionDefinition:
    name: str
    version: str = "1.0.0"
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    permissions: frozenset[str] = frozenset()
    timeout: float = 10.0
    metadata: dict[str, Any] = field(default_factory=dict)
    scope: str = "global"
    project_id: str | None = None
    environment: str | None = None


def _validate_schema(value: Any, schema: dict[str, Any], label: str) -> None:
    if not schema: return
    expected = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool}
    if expected in types and not isinstance(value, types[expected]): raise ValidationError(f"{label} must be {expected}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value: raise ValidationError(f"Missing required {label} field: {key}")
        for key, child in schema.get("properties", {}).items():
            if key in value: _validate_schema(value[key], child, f"{label}.{key}")
    if isinstance(value, list) and schema.get("items"):
        for item in value: _validate_schema(item, schema["items"], label)

class FunctionAction:
    def __init__(self, name: str, handler: Callable[..., Awaitable[Any]], *, required_permissions: set[str] | None = None, description: str = "", input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None, timeout: float = 10.0, version: str = "1.0.0", metadata: dict[str, Any] | None = None, scope: str = "global", project_id: str | None = None, environment: str | None = None):
        if not inspect.iscoroutinefunction(handler): raise ValidationError("Action handler must be async")
        if timeout <= 0: raise ValidationError("Action timeout must be positive")
        self.name, self.handler, self.required_permissions = name, handler, required_permissions or set()
        self.version, self.description, self.input_schema, self.output_schema = version, description, input_schema or {}, output_schema or {}
        self.timeout, self.metadata, self.scope, self.project_id, self.environment = timeout, metadata or {}, scope, project_id, environment
    async def execute(self, context):
        permissions = set(getattr(context, "permissions", set()) or getattr(getattr(context, "request", None), "permissions", set()) or [])
        if not self.required_permissions.issubset(permissions) and "*" not in permissions: raise AuthorizationError(f"Missing action permissions: {sorted(self.required_permissions - permissions)}")
        processing = getattr(context, "processing", context)
        safe = DeveloperActionContext(getattr(processing, "user", None), getattr(processing, "session", None), getattr(processing, "message", None), getattr(getattr(processing, "nlu_result", None), "intent", None), list(getattr(getattr(processing, "nlu_result", None), "entities", []) or []), dict(getattr(processing, "metadata", {}) or {}), getattr(processing, "project", None), getattr(processing, "logger", None), getattr(getattr(processing, "request", None), "request_id", None), getattr(getattr(processing, "request", None), "trace_id", None), getattr(context, "tools", None))
        _validate_schema(safe, self.input_schema, "action input")
        try:
            result = await asyncio.wait_for(self.handler(safe), timeout=self.timeout)
            _validate_schema(result, self.output_schema, "action output")
            return result
        except asyncio.TimeoutError as exc: raise ActionError(f"Action timed out: {self.name}", details={"action": self.name, "timeout": self.timeout}) from exc
        except (ActionError, AuthorizationError, ValidationError): raise
        except Exception as exc: raise ActionError(f"Action failed: {self.name}") from exc
    def __call__(self, *args, **kwargs): return self.handler(*args, **kwargs)

class FunctionTool:
    def __init__(self, name: str, handler: Callable[..., Awaitable[Any]], *, required_permissions: set[str] | None = None, description: str = "", input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None, timeout: float = 10.0, version: str = "1.0.0", metadata: dict[str, Any] | None = None, scope: str = "global", project_id: str | None = None, environment: str | None = None):
        if not inspect.iscoroutinefunction(handler): raise ValidationError("Tool handler must be async")
        if timeout <= 0: raise ValidationError("Tool timeout must be positive")
        self.name, self.handler, self.required_permissions = name, handler, required_permissions or set()
        self.version, self.description, self.input_schema, self.output_schema = version, description, input_schema or {}, output_schema or {}
        self.timeout, self.metadata, self.scope, self.project_id, self.environment = timeout, metadata or {}, scope, project_id, environment
    async def execute(self, **kwargs):
        permissions = set(kwargs.pop("_permissions", set()) or [])
        if not self.required_permissions.issubset(permissions) and "*" not in permissions: raise AuthorizationError(f"Missing tool permissions: {sorted(self.required_permissions - permissions)}")
        depth = int(kwargs.pop("_execution_depth", 0))
        max_depth = int(self.metadata.get("max_execution_depth", 3))
        if depth >= max_depth: raise ToolError(f"Tool execution depth exceeded: {self.name}")
        _validate_schema(kwargs, self.input_schema, "tool input")
        try:
            result = await asyncio.wait_for(self.handler(**kwargs), timeout=self.timeout)
            _validate_schema(result, self.output_schema, "tool output")
            return result
        except asyncio.TimeoutError as exc: raise ToolError(f"Tool timed out: {self.name}", details={"tool": self.name, "timeout": self.timeout}) from exc
        except (ToolError, AuthorizationError, ValidationError): raise
        except Exception as exc: raise ToolError(f"Tool failed: {self.name}") from exc
    def __call__(self, *args, **kwargs): return self.handler(*args, **kwargs)

def action(name: str, *, required_permissions: set[str] | None = None, description: str = "", input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None, timeout: float = 10.0, version: str = "1.0.0", metadata: dict[str, Any] | None = None, scope: str = "global", project_id: str | None = None, environment: str | None = None):
    def decorate(handler): return FunctionAction(name, handler, required_permissions=required_permissions, description=description, input_schema=input_schema, output_schema=output_schema, timeout=timeout, version=version, metadata=metadata, scope=scope, project_id=project_id, environment=environment)
    return decorate

def tool(name: str, *, required_permissions: set[str] | None = None, description: str = "", input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None, timeout: float = 10.0, version: str = "1.0.0", metadata: dict[str, Any] | None = None, scope: str = "global", project_id: str | None = None, environment: str | None = None):
    def decorate(handler): return FunctionTool(name, handler, required_permissions=required_permissions, description=description, input_schema=input_schema, output_schema=output_schema, timeout=timeout, version=version, metadata=metadata, scope=scope, project_id=project_id, environment=environment)
    return decorate

class FunctionMiddleware:
    def __init__(self, name: str, handler: Callable[..., Awaitable[Any]], *, priority: int = 100, security: bool = False, scope: str = "global", project_id: str | None = None):
        if not inspect.iscoroutinefunction(handler): raise ValidationError("Middleware handler must be async")
        self.name, self.handler, self.priority, self.security, self.scope, self.project_id = name, handler, priority, security, scope, project_id
    async def __call__(self, context, next_handler): return await self.handler(context, next_handler)

def middleware(name: str, *, priority: int = 100, security: bool = False, scope: str = "global", project_id: str | None = None):
    def decorate(handler): return FunctionMiddleware(name, handler, priority=priority, security=security, scope=scope, project_id=project_id)
    return decorate
