from __future__ import annotations
from framework.sdk.transport import Transport, AsyncTransport
from framework.sdk.types import MessageResponse

class Messages:
    def __init__(self, transport): self.t = transport
    def create(self, text: str, *, project_id: str = "", user_id: str = "sdk-user", session_id: str | None = None, metadata: dict | None = None, idempotency_key: str | None = None):
        result = self.t.request("POST", "/api/v1/messages", json={"project_id": project_id, "user_id": user_id, "text": text, "session_id": session_id, "metadata": metadata or {}}, idempotency_key=idempotency_key, retries=2 if idempotency_key else 0)
        return MessageResponse(result.data, result.success, result.request_id, result.error)
    async def acreate(self, text: str, *, project_id: str = "", user_id: str = "sdk-user", session_id: str | None = None, metadata: dict | None = None, idempotency_key: str | None = None):
        result = await self.t.request("POST", "/api/v1/messages", json={"project_id": project_id, "user_id": user_id, "text": text, "session_id": session_id, "metadata": metadata or {}}, idempotency_key=idempotency_key, retries=2 if idempotency_key else 0)
        return MessageResponse(result.data, result.success, result.request_id, result.error)

class Resource:
    def __init__(self, transport, path): self.t, self.path = transport, path
    def list(self, project_id: str): return self.t.request("GET", f"/api/v1/projects/{project_id}/{self.path}")
    def get(self, resource_id: str): return self.t.request("GET", f"/api/v1/{self.path}/{resource_id}")

class Webhooks:
    def __init__(self, transport): self.t = transport
    def create(self, project_id: str, url: str, events: list[str], *, timeout_seconds: float = 10, max_retries: int = 3, idempotency_key: str | None = None):
        return self.t.request("POST", f"/api/v1/projects/{project_id}/webhooks", json={"url": url, "events": events, "timeout_seconds": timeout_seconds, "max_retries": max_retries}, idempotency_key=idempotency_key, retries=2 if idempotency_key else 0)
    def list(self, project_id: str): return self.t.request("GET", f"/api/v1/projects/{project_id}/webhooks")
    def delete(self, project_id: str, webhook_id: str): return self.t.request("DELETE", f"/api/v1/projects/{project_id}/webhooks/{webhook_id}")
    def deliveries(self, project_id: str, limit: int = 100): return self.t.request("GET", f"/api/v1/projects/{project_id}/webhooks/deliveries?limit={limit}")

class ModelSelection:
    def __init__(self, transport): self.t = transport
    def select(self, project_id: str, model_id: str, version: str, *, environment: str = "production", reason: str = ""):
        return self.t.request("POST", f"/api/v1/projects/{project_id}/model-selection", json={"model_id": model_id, "version": version, "environment": environment, "reason": reason})
    async def aselect(self, project_id: str, model_id: str, version: str, *, environment: str = "production", reason: str = ""):
        return await self.t.request("POST", f"/api/v1/projects/{project_id}/model-selection", json={"model_id": model_id, "version": version, "environment": environment, "reason": reason})

class Extensions:
    def __init__(self, transport): self.t = transport
    def list(self, project_id: str): return self.t.request("GET", f"/api/v1/projects/{project_id}/extensions")
    def health(self): return self.t.request("GET", "/health/extensions")

class Quota:
    def __init__(self, transport): self.t = transport
    def get(self, project_id: str): return self.t.request("GET", f"/api/v1/projects/{project_id}/quota")
    def usage(self, project_id: str, limit: int = 100): return self.t.request("GET", f"/api/v1/projects/{project_id}/usage?limit={limit}")

class Client:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 30.0):
        self.transport = Transport(api_key, base_url, timeout)
        self.messages = Messages(self.transport); self.projects = Resource(self.transport, "projects"); self.datasets = Resource(self.transport, "datasets"); self.training = Resource(self.transport, "training"); self.models = Resource(self.transport, "models"); self.bots = Resource(self.transport, "bots"); self.api_keys = Resource(self.transport, "api-keys")
        self.webhooks = Webhooks(self.transport); self.model_selection = ModelSelection(self.transport); self.extensions = Extensions(self.transport); self.quota = Quota(self.transport)
    def close(self): self.transport.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

class AsyncMessages(Messages):
    async def create(self, text: str, *, project_id: str = "", user_id: str = "sdk-user", session_id: str | None = None, metadata: dict | None = None, idempotency_key: str | None = None): return await self.acreate(text, project_id=project_id, user_id=user_id, session_id=session_id, metadata=metadata, idempotency_key=idempotency_key)

class AsyncModelSelection(ModelSelection):
    async def select(self, project_id: str, model_id: str, version: str, *, environment: str = "production", reason: str = ""):
        return await self.t.request("POST", f"/api/v1/projects/{project_id}/model-selection", json={"model_id": model_id, "version": version, "environment": environment, "reason": reason})

class AsyncWebhooks(Webhooks):
    async def create(self, project_id: str, url: str, events: list[str], *, timeout_seconds: float = 10, max_retries: int = 3, idempotency_key: str | None = None): return await self.t.request("POST", f"/api/v1/projects/{project_id}/webhooks", json={"url": url, "events": events, "timeout_seconds": timeout_seconds, "max_retries": max_retries}, idempotency_key=idempotency_key, retries=2 if idempotency_key else 0)
    async def list(self, project_id: str): return await self.t.request("GET", f"/api/v1/projects/{project_id}/webhooks")
    async def delete(self, project_id: str, webhook_id: str): return await self.t.request("DELETE", f"/api/v1/projects/{project_id}/webhooks/{webhook_id}")
    async def deliveries(self, project_id: str, limit: int = 100): return await self.t.request("GET", f"/api/v1/projects/{project_id}/webhooks/deliveries?limit={limit}")

class AsyncResource:
    def __init__(self, transport, path): self.t, self.path = transport, path
    async def list(self, project_id: str): return await self.t.request("GET", f"/api/v1/projects/{project_id}/{self.path}")
    async def get(self, resource_id: str): return await self.t.request("GET", f"/api/v1/{self.path}/{resource_id}")

class AsyncExtensions(Extensions):
    async def list(self, project_id: str): return await self.t.request("GET", f"/api/v1/projects/{project_id}/extensions")
    async def health(self): return await self.t.request("GET", "/health/extensions")

class AsyncQuota(Quota):
    async def get(self, project_id: str): return await self.t.request("GET", f"/api/v1/projects/{project_id}/quota")
    async def usage(self, project_id: str, limit: int = 100): return await self.t.request("GET", f"/api/v1/projects/{project_id}/usage?limit={limit}")

class AsyncClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 30.0):
        self.transport = AsyncTransport(api_key, base_url, timeout)
        self.messages = AsyncMessages(self.transport); self.projects = AsyncResource(self.transport, "projects"); self.datasets = AsyncResource(self.transport, "datasets"); self.training = AsyncResource(self.transport, "training"); self.models = AsyncResource(self.transport, "models"); self.bots = AsyncResource(self.transport, "bots"); self.api_keys = AsyncResource(self.transport, "api-keys")
        self.webhooks = AsyncWebhooks(self.transport); self.model_selection = AsyncModelSelection(self.transport); self.extensions = AsyncExtensions(self.transport); self.quota = AsyncQuota(self.transport)
    async def aclose(self): await self.transport.aclose()
    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.aclose()

__all__ = ["Client", "AsyncClient"]
