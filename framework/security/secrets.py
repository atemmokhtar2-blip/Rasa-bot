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

import httpx

class HttpSecretProvider(SecretProvider):
    def __init__(self, base_url: str, token: str, timeout: float = 5.0):
        if not base_url.startswith("https://"): raise ValueError("Secret manager must use HTTPS")
        self.base_url, self.token, self.timeout = base_url.rstrip("/"), token, timeout
    async def get_async(self, name: str) -> str | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/secrets/{name}", headers={"Authorization": f"Bearer {self.token}"})
            if response.status_code == 404: return None
            response.raise_for_status()
            data = response.json()
            return data.get("value")
