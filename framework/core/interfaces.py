from abc import ABC, abstractmethod
from typing import Any, Protocol
from framework.core.models import Entity, IncomingMessage, IntentPrediction, OutgoingResponse

class NLUProvider(ABC):
    @abstractmethod
    async def detect_intent(self, message: IncomingMessage, context: dict[str, Any]) -> IntentPrediction: ...
    @abstractmethod
    async def extract_entities(self, message: IncomingMessage, context: dict[str, Any]) -> list[Entity]: ...

class ChannelAdapter(ABC):
    @abstractmethod
    async def normalize(self, payload: Any, *, project_id: str) -> IncomingMessage: ...
    @abstractmethod
    async def send(self, response: OutgoingResponse, *, recipient_id: str) -> Any: ...

class Action(ABC):
    name: str
    version: str = "1.0.0"
    required_permissions: set[str] = set()
    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> OutgoingResponse: ...

class Tool(ABC):
    name: str
    version: str = "1.0.0"
    required_permissions: set[str] = set()
    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any: ...

class StorageProvider(Protocol):
    async def upload(self, key: str, content: bytes) -> str: ...
    async def download(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...

class QueueProvider(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> str: ...
    async def consume(self, topic: str) -> dict[str, Any] | None: ...
