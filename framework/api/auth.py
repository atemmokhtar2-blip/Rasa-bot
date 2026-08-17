from fastapi import Request
from framework.core.container import ApplicationContainer
from framework.errors import AuthenticationError, AuthorizationError

async def authenticate_api_request(request: Request, container: ApplicationContainer, api_key: str | None = None):
    if not api_key:
        if container.settings.app_env == "development":
            return None
        raise AuthenticationError("X-API-Key header is required")
    record = await container.developers.authenticate(api_key)
    request.state.api_key = record
    if not container.rate_limiter.allow(f"key:{record.key_id}"):
        raise AuthorizationError("Rate limit exceeded")
    return record

def require_permission(record, permission: str) -> None:
    if record is not None and permission not in record.permissions and "*" not in record.permissions:
        raise AuthorizationError(f"Missing permission: {permission}")
