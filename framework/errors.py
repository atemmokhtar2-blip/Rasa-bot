class FrameworkError(Exception):
    code = "FRAMEWORK_ERROR"
    status_code = 500

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

class AuthenticationError(FrameworkError):
    code, status_code = "INVALID_API_KEY", 401
class AuthorizationError(FrameworkError):
    code, status_code = "FORBIDDEN", 403
class RateLimitError(FrameworkError):
    code, status_code = "RATE_LIMIT_EXCEEDED", 429
class ValidationError(FrameworkError):
    code, status_code = "VALIDATION_ERROR", 422
class NotFoundError(FrameworkError):
    code, status_code = "NOT_FOUND", 404
class ExtensionError(FrameworkError):
    code = "EXTENSION_ERROR"
class PluginError(ExtensionError):
    code = "PLUGIN_ERROR"
class ProviderError(ExtensionError):
    code = "PROVIDER_ERROR"
class ModelError(FrameworkError):
    code = "MODEL_ERROR"
class NLUProviderError(ModelError):
    code = "NLU_PROVIDER_UNAVAILABLE"
class ActionError(FrameworkError):
    code = "ACTION_ERROR"
class ToolError(FrameworkError):
    code = "TOOL_ERROR"
class TransportError(FrameworkError):
    code = "TRANSPORT_ERROR"
