class SDKError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None, request_id: str | None = None, details: dict | None = None):
        super().__init__(message); self.message, self.status_code, self.code, self.request_id, self.details = message, status_code, code, request_id, details or {}
class APIError(SDKError): pass
class AuthenticationError(APIError): pass
class PermissionError(APIError): pass
class NotFoundError(APIError): pass
class ValidationError(APIError): pass
class RateLimitError(APIError):
    @property
    def retry_after(self) -> int | None: return self.details.get("retry_after")
class TransportError(SDKError): pass
