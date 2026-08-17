from typing import Any
from framework.core.events import EventBus, FrameworkEvent
from framework.core.interfaces import NLUProvider
from framework.core.models import IncomingMessage, OutgoingResponse, ProcessingResult
from framework.core.registries import ActionRegistry
from framework.errors import ActionError

class FrameworkEngine:
    def __init__(self, nlu: NLUProvider, events: EventBus, actions: ActionRegistry, intent_threshold: float = 0.55):
        self.nlu, self.events, self.actions = nlu, events, actions
        self.intent_threshold = intent_threshold

    async def process_message(self, message: IncomingMessage) -> ProcessingResult:
        trace = ["MESSAGE_RECEIVED"]
        await self.events.emit(FrameworkEvent("MESSAGE_RECEIVED", {"message_id": message.message_id}))
        context = message.metadata.get("context", {})
        intent = await self.nlu.detect_intent(message, context)
        trace.append("INTENT_DETECTED")
        entities = await self.nlu.extract_entities(message, context)
        trace.append("ENTITY_EXTRACTED")
        await self.events.emit(FrameworkEvent("INTENT_DETECTED", {"intent": intent.name, "confidence": intent.confidence}))
        if intent.confidence < self.intent_threshold:
            response = OutgoingResponse(text="لم أفهم الطلب بشكل كافٍ. هل يمكنك توضيحه؟")
            trace.append("FALLBACK")
        else:
            action = self.actions.resolve(intent.name)
            if action is None:
                response = OutgoingResponse(text="تم فهم الطلب، لكن لا يوجد إجراء مسجل له بعد.")
                trace.append("NO_ACTION")
            else:
                try:
                    response = await action.execute({"message": message, "intent": intent, "entities": entities, "context": context})
                    trace.append("ACTION_COMPLETED")
                except Exception as exc:
                    await self.events.emit(FrameworkEvent("ACTION_FAILED", {"action": intent.name, "error": str(exc)}))
                    raise ActionError("Action execution failed") from exc
        trace.append("RESPONSE")
        await self.events.emit(FrameworkEvent("MESSAGE_PROCESSED", {"message_id": message.message_id, "trace": trace}))
        return ProcessingResult(response=response, intent=intent, entities=entities, trace=trace)
