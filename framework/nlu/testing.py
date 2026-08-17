from framework.core.interfaces import NLUProvider
from framework.core.models import Entity, IncomingMessage, IntentPrediction, NLUResult, ProcessingContext

class FakeNLUProvider(NLUProvider):
    def __init__(self, intent: str = "get_order_status", confidence: float = 0.98, entities: list[Entity] | None = None): self.intent, self.confidence, self.entities = intent, confidence, entities or []
    async def analyze(self, message: IncomingMessage, context: ProcessingContext) -> NLUResult:
        return NLUResult(IntentPrediction(self.intent, self.confidence), list(self.entities), provider="fake", model_version="test")
    async def detect_intent(self, message: IncomingMessage, context: dict): return IntentPrediction(self.intent, self.confidence)
    async def extract_entities(self, message: IncomingMessage, context: dict): return list(self.entities)
