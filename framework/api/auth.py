from fastapi import Request
import inspect
from framework.core.container import ApplicationContainer
from framework.errors import AuthenticationError, AuthorizationError, RateLimitError

async def authenticate_api_request(request: Request, container: ApplicationContainer, api_key: str | None = None):
    supplied = api_key or request.headers.get("Authorization")
    if supplied and supplied.lower().startswith("bearer "): supplied = supplied[7:].strip()
    if not supplied:
        if container.settings.app_env == "development": return None
        raise AuthenticationError("API key is required")
    record = await container.developers.authenticate(supplied)
    record.permissions = container.permissions.expand(record.permissions)
    request.state.api_key = record
    request.state.gateway_context = {"api_key_id": record.key_id, "project_id": record.project_id, "environment": record.environment}
    allowed = container.rate_limiter.allow(f"key:{record.key_id}")
    if inspect.isawaitable(allowed): allowed = await allowed
    if not allowed: raise RateLimitError("Rate limit exceeded", details={"retry_after": 60})
    return record

def require_permission(record, permission: str) -> None:
    if record is not None and permission not in record.permissions and "*" not in record.permissions:
        raise AuthorizationError(f"Missing permission: {permission}")
