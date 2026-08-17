import inspect
import time
from framework.core.events import EventBus, FrameworkEvent
from framework.core.interfaces import NLUProvider
from framework.core.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from framework.core.models import ActionContext, ActionResult, Conversation, FrameworkUser, IncomingMessage, NLUResult, OutgoingResponse, PolicyResult, ProcessingContext, ProcessingResult, RequestContext
from framework.core.registries import ActionRegistry
from framework.core.response import ResponseBuilder
from framework.core.state import ContextEngine, ConversationManager, DialogueManager, PolicyEngine, SessionManager, UserResolver
from framework.nlu.registry import EntityRegistry
from framework.errors import ActionError, AuthorizationError
from framework.observability import AuditEvent, AuditLogger, UsageEvent, UsageMeter
from framework.observability.metrics import MetricsRegistry

class FrameworkEngine:
    def __init__(self, nlu: NLUProvider, events: EventBus, actions: ActionRegistry, intent_threshold: float = 0.55, sessions: SessionManager | None = None, context_engine: ContextEngine | None = None, dialogue: DialogueManager | None = None, policy: PolicyEngine | None = None, usage: UsageMeter | None = None, audit: AuditLogger | None = None, entities: EntityRegistry | None = None, response_builder: ResponseBuilder | None = None, idempotency: IdempotencyStore | None = None, metrics: MetricsRegistry | None = None, conversations: ConversationManager | None = None, users: UserResolver | None = None):
        self.nlu, self.events, self.actions = nlu, events, actions
        self.intent_threshold = intent_threshold
        self.sessions = sessions or SessionManager()
        self.context_engine = context_engine or ContextEngine()
        self.dialogue = dialogue or DialogueManager()
        self.policy = policy or PolicyEngine(intent_threshold)
        self.usage = usage or UsageMeter()
        self.audit = audit or AuditLogger()
        self.entities = entities or EntityRegistry()
        self.responses = response_builder or ResponseBuilder()
        self.idempotency = idempotency or InMemoryIdempotencyStore()
        self.metrics = metrics or MetricsRegistry()
        self.conversations = conversations or ConversationManager()
        self.users = users or UserResolver()

    async def _event(self, name: str, ctx: ProcessingContext, payload: dict, critical: bool = False) -> None:
        await self.events.emit(FrameworkEvent(name, payload, request_id=ctx.request.request_id, trace_id=ctx.request.trace_id, project_id=ctx.message.project_id, user_id=ctx.message.user_id, session_id=getattr(ctx.session, "id", None), critical=critical))

    async def process_message(self, message: IncomingMessage) -> ProcessingResult:
        started = time.perf_counter()
        request = RequestContext(project_id=message.project_id, user_id=message.user_id, channel=message.channel, metadata=dict(message.metadata))
        identity = __import__('framework.core.models', fromlist=['ChannelIdentity']).ChannelIdentity(message.channel, message.user_id, message.chat_id, dict(message.metadata))
        user = await self.users.resolve(message.project_id, identity)
        conversation = await self.conversations.get_or_create(message.project_id, user.user_id, message.conversation_id or message.chat_id)
        ctx = ProcessingContext(message=message, request=request, user=user, conversation=conversation)
        previous = await self.idempotency.get(message.idempotency_key)
        if previous is not None: return previous
        self.metrics.inc("messages_received_total")
        trace = ["MESSAGE_RECEIVED", "VALIDATE_MESSAGE", "RESOLVE_PROJECT", "RESOLVE_USER", "RESOLVE_CONVERSATION"]
        await self.usage.record(UsageEvent(message.project_id, "messages", request_id=request.request_id))
        await self._event("MESSAGE_RECEIVED", ctx, {"message_id": message.message_id})
        await self._event("PROJECT_RESOLVED", ctx, {"project_id": message.project_id})
        await self._event("SESSION_CREATED", ctx, {"conversation_id": ctx.conversation.conversation_id})
        session_start = time.perf_counter()
        ctx.session = await self.sessions.get_or_create(message.project_id, message.user_id, ctx.conversation.conversation_id)
        ctx.timings["session_ms"] = (time.perf_counter() - session_start) * 1000
        trace += ["RESOLVE_SESSION", "LOAD_CONTEXT"]
        ctx.metadata = dict(ctx.session.context)
        ctx.metadata.update(message.metadata.get("context", {}))
        await self._event("SESSION_LOADED", ctx, {"session_id": ctx.session.id})
        nlu_start = time.perf_counter()
        try:
            self.metrics.inc("nlu_requests_total")
            ctx.nlu_result = await self.nlu.analyze(message, ctx)
        except Exception as exc:
            self.metrics.inc("nlu_failures_total")
            await self._event("PROCESSING_FAILED", ctx, {"code": "NLU_PROVIDER_UNAVAILABLE", "error": str(exc)})
            raise
        ctx.timings["nlu_ms"] = (time.perf_counter() - nlu_start) * 1000
        trace += ["RUN_NLU", "DETECT_INTENT", "EXTRACT_ENTITIES"]
        if self.entities.names(): ctx.nlu_result.entities = self.entities.normalize_and_validate(ctx.nlu_result.entities)
        await self._event("NLU_COMPLETED", ctx, {"provider": ctx.nlu_result.provider, "intent": ctx.nlu_result.intent.name})
        await self._event("INTENT_DETECTED", ctx, {"intent": ctx.nlu_result.intent.name, "confidence": ctx.nlu_result.confidence})
        await self._event("ENTITIES_EXTRACTED", ctx, {"count": len(ctx.nlu_result.entities)})
        ctx.dialogue_state = self.context_engine.build(ctx.session, ctx.nlu_result.intent, ctx.nlu_result.entities)
        self.dialogue.next_state(ctx.session, ctx.nlu_result.intent, ctx.nlu_result.entities)
        trace.append("UPDATE_DIALOGUE_STATE")
        policy_start = time.perf_counter()
        decision = self.policy.decide(ctx.nlu_result.intent, ctx.session, set(self.actions.names()))
        policy = PolicyResult(decision={"fallback": "FALLBACK", "clarification": "ASK_CLARIFICATION", "action": "EXECUTE_ACTION"}.get(decision.kind, decision.kind.upper()), action=decision.target, fallback=decision.kind == "fallback", reason=decision.reason, required_entities=list(getattr(ctx.session, "required_entities", [])))
        ctx.policy_result = policy
        ctx.timings["policy_ms"] = (time.perf_counter() - policy_start) * 1000
        trace.append("RUN_POLICY")
        await self._event("POLICY_DECIDED", ctx, {"decision": policy.decision, "action": policy.action})
        action_result: ActionResult | OutgoingResponse | None = None
        action_name = None
        if policy.decision == "FALLBACK": trace.append("FALLBACK")
        if policy.decision == "ASK_CLARIFICATION": trace.append("CLARIFICATION_REQUIRED")
        if policy.decision == "EXECUTE_ACTION" and policy.action:
            action_name = policy.action
            action = self.actions.resolve(policy.action)
            if action is None: policy = PolicyResult("ASK_CLARIFICATION", reason="action_not_found")
            else:
                trace += ["RESOLVE_ACTION", "AUTHORIZE_ACTION"]
                permissions = set(message.metadata.get("permissions", []))
                required = set(getattr(action, "required_permissions", set()))
                if required - permissions and "*" not in permissions: raise AuthorizationError(f"Missing action permissions: {sorted(required - permissions)}")
                action_start = time.perf_counter()
                await self._event("ACTION_STARTED", ctx, {"action": action_name})
                try:
                    result = await action.execute(ActionContext(ctx, permissions))
                    self.metrics.inc("actions_executed_total", action=action_name or "unknown")
                    action_result = result
                    trace += ["EXECUTE_ACTION", "ACTION_COMPLETED"]
                    await self._event("ACTION_COMPLETED", ctx, {"action": action_name})
                except AuthorizationError: raise
                except Exception as exc:
                    self.metrics.inc("actions_failed_total", action=action_name or "unknown")
                    await self._event("ACTION_FAILED", ctx, {"action": action_name, "error": str(exc)})
                    raise ActionError("Action execution failed") from exc
                ctx.timings["action_ms"] = (time.perf_counter() - action_start) * 1000
        response_start = time.perf_counter()
        response = self.responses.build(policy, action_result)
        ctx.timings["response_ms"] = (time.perf_counter() - response_start) * 1000
        trace.append("BUILD_RESPONSE")
        ctx.session.context.update(ctx.metadata)
        trace += ["UPDATE_CONTEXT", "PERSIST_RESULT", "EMIT_EVENTS", "MESSAGE_PROCESSED", "RESPONSE"]
        ctx.timings["total_ms"] = (time.perf_counter() - started) * 1000
        self.metrics.inc("messages_processed_total")
        result = ProcessingResult(response=response, intent=ctx.nlu_result.intent, entities=ctx.nlu_result.entities, request_id=request.request_id, trace=trace, trace_id=request.trace_id, confidence=ctx.nlu_result.confidence, action=action_name, session_id=ctx.session.id, metadata={"provider": ctx.nlu_result.provider}, timings=ctx.timings)
        await self.idempotency.put(message.idempotency_key, result)
        await self._event("RESPONSE_CREATED", ctx, {"action": action_name})
        await self._event("MESSAGE_PROCESSED", ctx, {"message_id": message.message_id, "trace": trace})
        await self.audit.record(AuditEvent("MESSAGE_PROCESSED", project_id=message.project_id, actor_id=message.user_id, changes={"intent": ctx.nlu_result.intent.name, "trace": trace}))
        return result
