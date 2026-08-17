from typing import Any
from framework.core.interfaces import NLUProvider
from framework.core.models import Entity, IncomingMessage, IntentPrediction

class RuleBasedNLUProvider(NLUProvider):
    """Deterministic development provider; replaceable by RasaProvider."""
    async def detect_intent(self, message: IncomingMessage, context: dict[str, Any]) -> IntentPrediction:
        text = (message.text or "").lower().strip()
        if text.startswith("/start") or "ابدأ" in text:
            return IntentPrediction("start", 0.99)
        if "مساعدة" in text or text.startswith("/help"):
            return IntentPrediction("help", 0.98)
        return IntentPrediction("fallback", 0.35)
    async def extract_entities(self, message: IncomingMessage, context: dict[str, Any]) -> list[Entity]:
        return []
