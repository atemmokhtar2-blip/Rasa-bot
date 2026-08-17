from typing import Any
import httpx
from framework.core.interfaces import NLUProvider
from framework.core.models import Entity, IncomingMessage, IntentPrediction
from framework.errors import ModelError

class RasaProvider(NLUProvider):
    def __init__(self, endpoint: str, timeout: float = 10.0):
        self.endpoint, self.timeout = endpoint.rstrip("/"), timeout
    async def _parse(self, message: IncomingMessage, context: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.endpoint}/model/parse", json={"text": message.text or "", "metadata": {"project_id": message.project_id, "user_id": message.user_id, "context": context or {}}}, headers={"X-Request-ID": message.message_id})
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            raise ModelError("Rasa provider request failed") from exc
    async def detect_intent(self, message: IncomingMessage, context: dict[str, Any]) -> IntentPrediction:
        data = await self._parse(message, context)
        intent = data.get("intent") or {}
        return IntentPrediction(intent.get("name", "fallback"), float(intent.get("confidence", 0.0)))
    async def extract_entities(self, message: IncomingMessage, context: dict[str, Any]) -> list[Entity]:
        return [Entity(e.get("entity", "unknown"), e.get("value"), float(e.get("confidence", 1.0)), e.get("start"), e.get("end"), e) for e in (await self._parse(message, context)).get("entities", [])
]
