from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from framework.core.models import ChannelIdentity, Conversation, Entity, FrameworkUser, IntentPrediction

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
    dialogue: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

class SessionManager:
    def __init__(self, timeout_minutes: int = 30): self.timeout = timedelta(minutes=timeout_minutes); self._sessions: dict[tuple[str, str, str], Session] = {}
    async def create_session(self, project_id: str, user_id: str, conversation_id: str) -> Session:
        session = Session(project_id=project_id, user_id=user_id, conversation_id=conversation_id, expires_at=datetime.now(timezone.utc) + self.timeout)
        self._sessions[(project_id, user_id, conversation_id)] = session
        return session
    async def get_session(self, session_id: str) -> Session | None: return next((session for session in self._sessions.values() if session.id == session_id), None)
    async def get_or_create(self, project_id: str, user_id: str, conversation_id: str) -> Session:
        key = (project_id, user_id, conversation_id); session = self._sessions.get(key); now = datetime.now(timezone.utc)
        if session is None or session.state == "ended" or (session.expires_at and now >= session.expires_at): session = await self.create_session(project_id, user_id, conversation_id)
        await self.touch_session(session); return session
    async def update_session(self, session: Session, **changes: Any) -> Session:
        for key, value in changes.items():
            if hasattr(session, key): setattr(session, key, value)
        return await self.touch_session(session)
    async def update(self, session: Session, **changes: Any) -> Session: return await self.update_session(session, **changes)
    async def touch_session(self, session: Session) -> Session:
        now = datetime.now(timezone.utc); session.updated_at = now; session.expires_at = now + self.timeout; return session
    async def close_session(self, session: Session) -> None: session.state = "ended"; await self.touch_session(session)
    async def end(self, session: Session) -> None: await self.close_session(session)
    async def is_active(self, session: Session) -> bool: return session.state == "active" and (session.expires_at is None or datetime.now(timezone.utc) < session.expires_at)

class ContextManager:
    def __init__(self): self._contexts: dict[str, dict[str, Any]] = {}
    async def get_context(self, session_id: str) -> dict[str, Any]: return dict(self._contexts.get(session_id, {}))
    async def set_context(self, session_id: str, context: dict[str, Any]) -> dict[str, Any]: self._contexts[session_id] = dict(context); return dict(self._contexts[session_id])
    async def update_context(self, session_id: str, changes: dict[str, Any]) -> dict[str, Any]: return await self.set_context(session_id, {**await self.get_context(session_id), **changes})
    async def delete_context(self, session_id: str) -> None: self._contexts.pop(session_id, None)
    async def merge_context(self, session_id: str, context: dict[str, Any]) -> dict[str, Any]: return await self.update_context(session_id, context)
    async def validate_context(self, context: dict[str, Any]) -> bool: return isinstance(context, dict)

class ConversationManager:
    def __init__(self): self._items: dict[str, Conversation] = {}
    async def get_or_create(self, project_id: str, user_id: str, conversation_id: str) -> Conversation:
        item = self._items.get(conversation_id)
        if item is None: item = Conversation(conversation_id, project_id, user_id); self._items[conversation_id] = item
        return item
    async def get(self, conversation_id: str) -> Conversation | None: return self._items.get(conversation_id)

class UserResolver:
    async def resolve(self, project_id: str, identity: ChannelIdentity) -> FrameworkUser:
        return FrameworkUser(f"{identity.channel}:{identity.external_user_id}", project_id, [identity], dict(identity.metadata))

class ContextEngine:
    def build(self, session: Session, intent: IntentPrediction | None, entities: list[Entity]) -> dict[str, Any]:
        context = dict(session.context)
        if intent: context.update({"previous_intent": context.get("current_intent"), "current_intent": intent.name, "confidence": intent.confidence})
        context["entities"] = {entity.name: entity.value for entity in entities}; context["session_id"] = session.id; session.context = context
        return context

class DialogueManager:
    def next_state(self, session: Session, intent: IntentPrediction, entities: list[Entity]) -> str:
        session.last_intent = intent.name
        if not entities and intent.name.startswith("book_"): session.state, session.required_entities = "waiting_for_entities", ["date", "time"]
        else: session.state, session.required_entities = "active", []
        return session.state

@dataclass
class PolicyDecision:
    kind: str
    target: str | None = None
    reason: str | None = None

class PolicyEngine:
    def __init__(self, confidence_threshold: float = 0.55): self.confidence_threshold = confidence_threshold
    def decide(self, intent: IntentPrediction, session: Session, available_actions: set[str]) -> PolicyDecision:
        if intent.confidence < self.confidence_threshold: return PolicyDecision("fallback", reason="low_confidence")
        if intent.name in available_actions: return PolicyDecision("action", target=intent.name)
        return PolicyDecision("clarification", reason="no_action_registered")
    async def decide_async(self, intent: IntentPrediction, session: Session, available_actions: set[str]) -> PolicyDecision: return self.decide(intent, session, available_actions)
