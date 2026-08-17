import asyncio
from typing import Any, Awaitable, Callable
from framework.errors import AuthorizationError, PluginError

class PluginRuntime:
    def __init__(self, timeout_seconds: float = 10.0): self.timeout_seconds = timeout_seconds
    async def execute(self, plugin_id: str, operation: Callable[[], Awaitable[Any]], granted_permissions: set[str], required_permissions: set[str]) -> Any:
        missing = required_permissions - granted_permissions
        if missing: raise AuthorizationError(f"Plugin {plugin_id} missing permissions: {sorted(missing)}")
        try:
            return await asyncio.wait_for(operation(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise PluginError(f"Plugin {plugin_id} exceeded execution timeout") from exc
        except PluginError:
            raise
        except Exception as exc:
            raise PluginError(f"Plugin {plugin_id} failed in isolated execution") from exc
