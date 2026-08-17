import json
from datetime import datetime
from framework.core.idempotency import IdempotencyStore
from framework.core.models import Entity, IntentPrediction, OutgoingResponse, ProcessingResult
from framework.infrastructure.redis import RedisProvider

class RedisIdempotencyStore(IdempotencyStore):
    def __init__(self, redis: RedisProvider, ttl_seconds: int = 86400): self.redis, self.ttl_seconds = redis, ttl_seconds
    async def get(self, key: str) -> ProcessingResult | None:
        raw = await self.redis.get(f"idempotency:{key}")
        if not raw: return None
        data = json.loads(raw); response = OutgoingResponse(**data["response"])
        intent = IntentPrediction(**data["intent"]) if data.get("intent") else None
        return ProcessingResult(response=response, intent=intent, entities=[Entity(**item) for item in data.get("entities", [])], request_id=data["request_id"], trace=data.get("trace", []), success=data.get("success", True), trace_id=data.get("trace_id"), confidence=data.get("confidence"), action=data.get("action"), session_id=data.get("session_id"), metadata=data.get("metadata", {}), errors=data.get("errors", []), timings=data.get("timings", {}))
    async def put(self, key: str, result: ProcessingResult) -> None:
        await self.redis.set(f"idempotency:{key}", json.dumps({"response": {"text": result.response.text, "messages": result.response.messages, "buttons": result.response.buttons, "keyboard": result.response.keyboard, "attachments": result.response.attachments, "metadata": result.response.metadata, "actions": result.response.actions, "parse_mode": result.response.parse_mode, "reply_to": result.response.reply_to}, "intent": {"name": result.intent.name, "confidence": result.intent.confidence, "metadata": result.intent.metadata} if result.intent else None, "entities": [{"name": e.name, "value": e.value, "confidence": e.confidence, "start": e.start, "end": e.end, "metadata": e.metadata} for e in result.entities], "request_id": result.request_id, "trace": result.trace, "success": result.success, "trace_id": result.trace_id, "confidence": result.confidence, "action": result.action, "session_id": result.session_id, "metadata": result.metadata, "errors": result.errors, "timings": result.timings}, default=str), self.ttl_seconds)
