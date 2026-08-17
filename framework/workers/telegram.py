from framework.infrastructure.queue import RedisQueue
from framework.channels.telegram import TelegramAdapter
from framework.core.container import ApplicationContainer
from framework.config import Settings

class TelegramWebhookWorker:
    def __init__(self, queue: RedisQueue, container: ApplicationContainer, settings: Settings): self.queue, self.container, self.settings, self.running = queue, container, settings, False
    async def run_once(self) -> bool:
        envelope = await self.queue.consume('telegram_updates', timeout=1)
        if not envelope: return False
        adapter = TelegramAdapter(self.settings.telegram_bot_token)
        message = await adapter.normalize(envelope['payload'], project_id=envelope['project_id'])
        result = await self.container.engine.process_message(message)
        await adapter.send(result.response, recipient_id=message.chat_id)
        return True
    async def run(self) -> None:
        self.running = True
        while self.running: await self.run_once()
    def stop(self) -> None: self.running = False
