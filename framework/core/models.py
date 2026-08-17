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
class ChannelIdentity:
    channel: str
    external_user_id: str
    external_chat_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class FrameworkUser:
    user_id: str
    project_id: str
    identities: list[ChannelIdentity] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class Conversation:
    conversation_id: str
    project_id: str
    user_id: str
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

    @property
    def idempotency_key(self) -> str:
        return self.metadata.get("idempotency_key") or self.channel_message_id or self.message_id

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
    def rendered_messages(self) -> list[str]: return self.messages or ([self.text] if self.text else [])

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
class NLUResult:
    intent: IntentPrediction
    entities: list[Entity] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    provider: str = "unknown"
    model_version: str | None = None
    processing_time_ms: float = 0.0
    @property
    def confidence(self) -> float: return self.intent.confidence

@dataclass(slots=True)
class RequestContext:
    request_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str | None = None
    developer_id: str | None = None
    user_id: str | None = None
    channel: str | None = None
    started_at: datetime = field(default_factory=now)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ProcessingContext:
    message: IncomingMessage
    request: RequestContext
    project: Any = None
    developer: Any = None
    user: FrameworkUser | None = None
    conversation: Conversation | None = None
    session: Any = None
    dialogue_state: Any = None
    nlu_result: NLUResult | None = None
    policy_result: Any = None
    action_result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)

@dataclass(slots=True)
class PolicyResult:
    decision: str
    action: str | None = None
    response_type: str | None = None
    required_entities: list[str] = field(default_factory=list)
    fallback: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ActionContext:
    processing: ProcessingContext
    permissions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    def __getitem__(self, key: str) -> Any:
        values = {"message": self.processing.message, "intent": self.processing.nlu_result.intent if self.processing.nlu_result else None, "entities": self.processing.nlu_result.entities if self.processing.nlu_result else [], "context": self.processing.metadata, "session": self.processing.session, "processing": self.processing}
        return values[key]

@dataclass(slots=True)
class ActionResult:
    success: bool
    data: Any = None
    response: OutgoingResponse | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

@dataclass(slots=True)
class ProcessingResult:
    response: OutgoingResponse
    intent: IntentPrediction | None = None
    entities: list[Entity] = field(default_factory=list)
    request_id: str = field(default_factory=lambda: str(uuid4()))
    trace: list[str] = field(default_factory=list)
    success: bool = True
    trace_id: str | None = None
    confidence: float | None = None
    action: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        entities = [{"name": entity.name, "value": entity.value, "confidence": entity.confidence, "start": entity.start, "end": entity.end, "metadata": entity.metadata} for entity in self.entities]
        response = {"text": self.response.text, "messages": self.response.messages, "buttons": self.response.buttons, "keyboard": self.response.keyboard, "attachments": self.response.attachments, "metadata": self.response.metadata, "actions": self.response.actions, "reply_to": self.response.reply_to}
        return {"success": self.success, "request_id": self.request_id, "trace_id": self.trace_id, "intent": self.intent.name if self.intent else None, "entities": entities, "confidence": self.confidence, "action": self.action, "response": response, "session_id": self.session_id, "metadata": self.metadata, "errors": self.errors, "timings": self.timings}
