from collections.abc import Mapping

SENSITIVE_NAMES = {"secret", "token", "password", "api_key", "authorization", "secret_hash", "telegram_bot_token"}

class SensitiveDataRedactor:
    def __init__(self, replacement: str = "[REDACTED]"): self.replacement = replacement
    def redact(self, value):
        if isinstance(value, Mapping):
            return {key: self.replacement if str(key).lower() in SENSITIVE_NAMES else self.redact(item) for key, item in value.items()}
        if isinstance(value, list): return [self.redact(item) for item in value]
        if isinstance(value, tuple): return tuple(self.redact(item) for item in value)
        return value
