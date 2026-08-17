import asyncio
import time
from typing import Any, Awaitable, Callable
from framework.errors import AuthorizationError, PluginError

class ExtensionRuntime:
    def __init__(self, timeout_seconds: float = 10.0, max_execution_depth: int = 3): self.timeout_seconds, self.max_execution_depth = timeout_seconds, max_execution_depth
    async def execute(self, plugin_id: str, operation: Callable[[], Awaitable[Any]], granted_permissions: set[str], required_permissions: set[str], *, request_id: str | None = None, trace_id: str | None = None, project_id: str | None = None, timeout: float | None = None, depth: int = 0) -> Any:
        missing = set(required_permissions) - set(granted_permissions)
        if missing: raise AuthorizationError(f"Plugin {plugin_id} missing permissions: {sorted(missing)}")
        if depth >= self.max_execution_depth: raise PluginError(f"Extension {plugin_id} execution depth exceeded")
        started = time.perf_counter()
        try:
            return await asyncio.wait_for(operation(), timeout=timeout or self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise PluginError(f"Plugin {plugin_id} exceeded execution timeout", details={"plugin_id": plugin_id, "request_id": request_id, "duration_ms": (time.perf_counter() - started) * 1000}) from exc
        except (PluginError, AuthorizationError): raise
        except Exception as exc:
            raise PluginError(f"Plugin {plugin_id} failed in isolated execution", details={"plugin_id": plugin_id, "request_id": request_id}) from exc

PluginRuntime = ExtensionRuntime
