from framework.infrastructure.queue import RedisQueue
from framework.channels.telegram import TelegramAdapter
from framework.core.container import ApplicationContainer
from framework.config import Settings

class TelegramWebhookWorker:
    def __init__(self, queue: RedisQueue, container: ApplicationContainer, settings: Settings): self.queue, self.container, self.settings, self.running = queue, container, settings, False
    async def run_once(self) -> bool:
        envelope = await self.queue.consume("telegram_updates", timeout=1)
        if not envelope: return False
        project_id = envelope["project_id"]
        bots = self.container.bots.list_for_project(project_id); bots = await bots if hasattr(bots, "__await__") else bots
        bot_id = envelope.get("bot_id")
        bot = next((item for item in bots if item.id == bot_id and item.project_id == project_id), None) if bot_id else next((item for item in bots if item.status == "enabled"), None)
        if bot is None or bot.status != "enabled": return False
        token = self.container.bot_secrets.get(bot.token_secret_ref)
        if not token: return False
        adapter = TelegramAdapter(token)
        message = await adapter.normalize(envelope["payload"], project_id=project_id)
        result = await self.container.messages.process(message)
        await adapter.send(result.response, recipient_id=message.chat_id)
        return True
    async def run(self) -> None:
        self.running = True
        while self.running: await self.run_once()
    def stop(self) -> None: self.running = False
