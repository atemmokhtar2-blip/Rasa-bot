from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

def now() -> datetime:
    return datetime.now(timezone.utc)

@dataclass(slots=True)
class Attachment:
    kind: str
    file_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class IncomingMessage:
    project_id: str
    channel: str
    user_id: str
    chat_id: str
    text: str | None = None
    message_id: str = field(default_factory=lambda: str(uuid4()))
    channel_message_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    timestamp: datetime = field(default_factory=now)
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    attachments: list[Attachment] = field(default_factory=list)

@dataclass(slots=True)
class OutgoingResponse:
    text: str | None = None
    messages: list[str] = field(default_factory=list)
    buttons: list[dict[str, Any]] = field(default_factory=list)
    keyboard: dict[str, Any] | None = None
    attachments: list[Attachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    parse_mode: str | None = None
    reply_to: str | None = None

    def rendered_messages(self) -> list[str]:
        return self.messages or ([self.text] if self.text else [])

@dataclass(slots=True)
class IntentPrediction:
    name: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class Entity:
    name: str
    value: Any
    confidence: float = 1.0
    start: int | None = None
    end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ProcessingResult:
    response: OutgoingResponse
    intent: IntentPrediction | None = None
    entities: list[Entity] = field(default_factory=list)
    request_id: str = field(default_factory=lambda: str(uuid4()))
    trace: list[str] = field(default_factory=list)
