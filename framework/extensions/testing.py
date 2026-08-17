from __future__ import annotations
from types import SimpleNamespace
from typing import Any
from framework.core.models import IncomingMessage, RequestContext, ProcessingContext
from framework.extensions.providers import FakeNLUProvider, FakeModelProvider, FakeStorageProvider, ChannelProvider

class MockContext:
    def __init__(self, *, project_id: str = "test-project", user_id: str = "test-user", text: str = "", permissions: set[str] | None = None, metadata: dict[str, Any] | None = None):
        message = IncomingMessage(project_id, "test", user_id, user_id, text=text, metadata=metadata or {})
        self.processing = ProcessingContext(message, RequestContext(project_id=project_id, user_id=user_id), metadata=metadata or {})
        self.permissions = permissions or set()
        self.project = SimpleNamespace(id=project_id)
        self.user = SimpleNamespace(id=user_id)
        self.session = None
        self.message = message
        self.metadata = metadata or {}
        self.logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)

class FakeTelegramProvider(ChannelProvider):
    name, version, channel = "fake-telegram", "1.0.0", "telegram"
    def __init__(self): self.sent = []
    async def normalize(self, payload, *, project_id):
        message = payload.get("message", payload)
        return IncomingMessage(project_id, self.channel, str(message.get("from", {}).get("id", "user")), str(message.get("chat", {}).get("id", "chat")), text=message.get("text"))
    async def send(self, response, *, recipient_id): self.sent.append((recipient_id, response.rendered_messages())); return {"recipient_id": recipient_id, "messages": response.rendered_messages()}

def provider_contract(provider: Any) -> None:
    for method in ("health",):
        if not callable(getattr(provider, method, None)): raise AssertionError(f"Provider contract missing {method}")

def extension_contract(extension: Any) -> None:
    for method in ("initialize", "shutdown"):
        if not callable(getattr(extension, method, None)): raise AssertionError(f"Extension contract missing {method}")
