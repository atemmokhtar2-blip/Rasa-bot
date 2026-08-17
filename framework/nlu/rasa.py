import time
from typing import Any
import httpx
from framework.core.interfaces import NLUProvider
from framework.core.models import Entity, IncomingMessage, IntentPrediction, NLUResult, ProcessingContext
from framework.errors import NLUProviderError

class RasaProvider(NLUProvider):
    def __init__(self, endpoint: str, timeout: float = 10.0, retries: int = 1):
        self.endpoint, self.timeout, self.retries = endpoint.rstrip("/"), timeout, retries

    async def _parse(self, message: IncomingMessage, context: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"text": message.text or "", "metadata": {"project_id": message.project_id, "user_id": message.user_id, "context": context or {}}}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(f"{self.endpoint}/model/parse", json=payload, headers={"X-Request-ID": message.message_id})
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict): raise ValueError("Rasa response must be an object")
                    return data
            except Exception as exc:
                last_error = exc
                if attempt < self.retries: continue
        raise NLUProviderError("Rasa provider request failed", details={"provider": "rasa", "cause": str(last_error)}) from last_error

    def _result(self, data: dict[str, Any], elapsed_ms: float) -> NLUResult:
        raw_intent = data.get("intent") or {}
        intent = IntentPrediction(str(raw_intent.get("name") or "fallback"), float(raw_intent.get("confidence", 0.0)), raw_intent)
        entities = [Entity(str(item.get("entity", "unknown")), item.get("value"), float(item.get("confidence", 1.0)), item.get("start"), item.get("end"), dict(item)) for item in data.get("entities", [])]
        return NLUResult(intent=intent, entities=entities, raw_metadata=data, provider="rasa", model_version=data.get("model_version"), processing_time_ms=elapsed_ms)

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.endpoint}/status")
                response.raise_for_status()
                return {"status": "ready", "provider": "rasa", "model_version": response.json().get("version") if response.headers.get("content-type", "").startswith("application/json") else None}
        except Exception as exc:
            return {"status": "unavailable", "provider": "rasa", "error": str(exc)}

    async def analyze(self, message: IncomingMessage, context: ProcessingContext) -> NLUResult:
        started = time.perf_counter()
        result = self._result(await self._parse(message, context.metadata), (time.perf_counter() - started) * 1000)
        return result

    async def detect_intent(self, message: IncomingMessage, context: dict[str, Any]) -> IntentPrediction:
        return (await self._result(await self._parse(message, context), 0).intent)

    async def extract_entities(self, message: IncomingMessage, context: dict[str, Any]) -> list[Entity]:
        return (await self._result(await self._parse(message, context), 0)).entities
