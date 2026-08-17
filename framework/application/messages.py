from framework.core.engine import FrameworkEngine
from framework.core.models import IncomingMessage, ProcessingResult

class MessageApplicationService:
    def __init__(self, engine: FrameworkEngine): self.engine = engine
    async def process(self, message: IncomingMessage) -> ProcessingResult: return await self.engine.process_message(message)
