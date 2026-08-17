from framework.core.events import EventBus, FrameworkEvent
from framework.core.interfaces import NLUProvider
from framework.core.models import IncomingMessage, OutgoingResponse, ProcessingResult
from framework.core.registries import ActionRegistry
from framework.core.state import ContextEngine, DialogueManager, PolicyEngine, SessionManager
from framework.nlu.registry import EntityRegistry
from framework.errors import ActionError
from framework.observability import AuditEvent, AuditLogger, UsageEvent, UsageMeter

class FrameworkEngine:
    def __init__(self, nlu: NLUProvider, events: EventBus, actions: ActionRegistry, intent_threshold: float = 0.55, sessions: SessionManager | None = None, context_engine: ContextEngine | None = None, dialogue: DialogueManager | None = None, policy: PolicyEngine | None = None, usage: UsageMeter | None = None, audit: AuditLogger | None = None, entities: EntityRegistry | None = None):
        self.nlu, self.events, self.actions = nlu, events, actions
        self.intent_threshold = intent_threshold
        self.sessions = sessions or SessionManager()
        self.context_engine = context_engine or ContextEngine()
        self.dialogue = dialogue or DialogueManager()
        self.policy = policy or PolicyEngine(intent_threshold)
        self.usage = usage or UsageMeter()
        self.audit = audit or AuditLogger()
        self.entities = entities or EntityRegistry()

    async def process_message(self, message: IncomingMessage) -> ProcessingResult:
        trace = ["MESSAGE_RECEIVED"]
        await self.usage.record(UsageEvent(message.project_id, "messages", request_id=message.message_id))
        await self.events.emit(FrameworkEvent("MESSAGE_RECEIVED", {"message_id": message.message_id}))
        conversation_id = message.conversation_id or message.chat_id
        session = await self.sessions.get_or_create(message.project_id, message.user_id, conversation_id)
        session_context = dict(session.context)
        session_context.update(message.metadata.get("context", {}))
        intent = await self.nlu.detect_intent(message, session_context)
        trace.append("INTENT_DETECTED")
        entities = await self.nlu.extract_entities(message, session_context)
        entities = self.entities.normalize_and_validate(entities) if self.entities.names() else entities
        trace.append("ENTITY_EXTRACTED")
        context = self.context_engine.build(session, intent, entities)
        self.dialogue.next_state(session, intent, entities)
        await self.events.emit(FrameworkEvent("INTENT_DETECTED", {"intent": intent.name, "confidence": intent.confidence, "session_id": session.id}))
        decision = self.policy.decide(intent, session, set(self.actions.names()))
        trace.append("POLICY_SELECTED")
        if decision.kind == "fallback":
            response = OutgoingResponse(text="لم أفهم الطلب بشكل كافٍ. هل يمكنك توضيحه؟")
            trace.append("FALLBACK")
        elif decision.kind == "clarification":
            response = OutgoingResponse(text="فهمت نوع الطلب، لكن أحتاج إلى تفاصيل إضافية لتنفيذه.")
            trace.append("CLARIFICATION_REQUIRED")
        else:
            action = self.actions.resolve(decision.target)
            trace.append("ACTION_SELECTED")
            try:
                response = await action.execute({"message": message, "intent": intent, "entities": entities, "context": context, "session": session})
                trace.append("ACTION_COMPLETED")
            except Exception as exc:
                await self.events.emit(FrameworkEvent("ACTION_FAILED", {"action": intent.name, "error": str(exc), "session_id": session.id}))
                raise ActionError("Action execution failed") from exc
        trace.append("RESPONSE")
        await self.events.emit(FrameworkEvent("MESSAGE_PROCESSED", {"message_id": message.message_id, "session_id": session.id, "trace": trace}))
        await self.audit.record(AuditEvent("MESSAGE_PROCESSED", project_id=message.project_id, changes={"intent": intent.name, "trace": trace}))
        return ProcessingResult(response=response, intent=intent, entities=entities, trace=trace)
