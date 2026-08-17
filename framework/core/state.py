from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from framework.core.models import Entity, IntentPrediction

@dataclass
class Session:
    project_id: str
    user_id: str
    conversation_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    state: str = "active"
    last_intent: str | None = None
    pending_action: str | None = None
    required_entities: list[str] = field(default_factory=list)
    user_metadata: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class SessionManager:
    def __init__(self, timeout_minutes: int = 30):
        self.timeout = timedelta(minutes=timeout_minutes)
        self._sessions: dict[tuple[str, str, str], Session] = {}

    async def get_or_create(self, project_id: str, user_id: str, conversation_id: str) -> Session:
        key = (project_id, user_id, conversation_id)
        session = self._sessions.get(key)
        if session is None or datetime.now(timezone.utc) - session.updated_at > self.timeout or session.state == "ended":
            session = Session(project_id=project_id, user_id=user_id, conversation_id=conversation_id)
            self._sessions[key] = session
        session.updated_at = datetime.now(timezone.utc)
        return session

    async def update(self, session: Session, **changes: Any) -> Session:
        for key, value in changes.items():
            if hasattr(session, key):
                setattr(session, key, value)
        session.updated_at = datetime.now(timezone.utc)
        return session

    async def end(self, session: Session) -> None:
        session.state = "ended"
        session.updated_at = datetime.now(timezone.utc)

class ContextEngine:
    def build(self, session: Session, intent: IntentPrediction | None, entities: list[Entity]) -> dict[str, Any]:
        context = dict(session.context)
        if intent:
            context["previous_intent"] = context.get("current_intent")
            context["current_intent"] = intent.name
            context["confidence"] = intent.confidence
        context["entities"] = {entity.name: entity.value for entity in entities}
        context["session_id"] = session.id
        session.context = context
        return context

class DialogueManager:
    def next_state(self, session: Session, intent: IntentPrediction, entities: list[Entity]) -> str:
        session.last_intent = intent.name
        if not entities and intent.name.startswith("book_"):
            session.state = "waiting_for_entities"
            session.required_entities = ["date", "time"]
        else:
            session.state = "active"
            session.required_entities = []
        return session.state

@dataclass
class PolicyDecision:
    kind: str
    target: str | None = None
    reason: str | None = None

class PolicyEngine:
    def __init__(self, confidence_threshold: float = 0.55):
        self.confidence_threshold = confidence_threshold

    def decide(self, intent: IntentPrediction, session: Session, available_actions: set[str]) -> PolicyDecision:
        if intent.confidence < self.confidence_threshold:
            return PolicyDecision("fallback", reason="low_confidence")
        if intent.name in available_actions:
            return PolicyDecision("action", target=intent.name)
        return PolicyDecision("clarification", reason="no_action_registered")
