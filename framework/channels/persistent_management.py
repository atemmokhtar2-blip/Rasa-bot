from datetime import datetime, timezone
from framework.channels.management import TelegramBot
from framework.infrastructure.domain_repositories import BotRepository
from framework.infrastructure.sql import BotORM

class PersistentBotRegistry:
    def __init__(self, repository: BotRepository): self.repository = repository
    async def register(self, bot: TelegramBot) -> TelegramBot:
        row = await self.repository.save(BotORM(id=bot.id, project_id=bot.project_id, name=bot.name, token_secret_ref=bot.token_secret_ref, status=bot.status, webhook_url=bot.webhook_url, webhook_secret_ref=bot.webhook_secret_ref, metadata_json=bot.metadata))
        return self._domain(row)
    async def list_for_project(self, project_id: str) -> list[TelegramBot]:
        rows = await self.repository.list_project(project_id)
        return [self._domain(row) for row in rows]
    async def get(self, bot_id: str) -> TelegramBot | None:
        row = await self.repository.get(bot_id)
        return self._domain(row) if row else None
    async def enable(self, bot_id: str) -> TelegramBot: return await self._set(bot_id, "enabled")
    async def disable(self, bot_id: str) -> TelegramBot: return await self._set(bot_id, "disabled")
    async def set_webhook(self, bot_id: str, url: str) -> TelegramBot:
        bot = await self.get(bot_id)
        if bot is None: raise KeyError(bot_id)
        async with self.repository.db.session() as session:
            row = await session.get(BotORM, bot_id); row.webhook_url = url; await session.commit(); await session.refresh(row); return self._domain(row)
    async def _set(self, bot_id: str, status: str) -> TelegramBot:
        return self._domain(await self.repository.set_status(bot_id, status))
    @staticmethod
    def _domain(row: BotORM) -> TelegramBot:
        return TelegramBot(row.project_id, row.name, row.token_secret_ref, id=row.id, status=row.status, webhook_url=row.webhook_url, webhook_secret_ref=row.webhook_secret_ref, metadata=dict(row.metadata_json or {}), created_at=row.created_at)
