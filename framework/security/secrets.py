import os
from framework.errors import FrameworkError

class SecretProvider:
    def get(self, name: str) -> str | None: raise NotImplementedError

class EnvironmentSecretProvider(SecretProvider):
    def __init__(self, environ: dict[str, str] | None = None): self.environ = environ or os.environ
    def get(self, name: str) -> str | None: return self.environ.get(name)
    def require(self, name: str) -> str:
        value = self.get(name)
        if not value: raise FrameworkError(f"Required secret is missing: {name}")
        return value
