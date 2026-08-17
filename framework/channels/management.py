from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

@dataclass
class TelegramBot:
    project_id: str
    name: str
    token_secret_ref: str
    id: str = field(default_factory=lambda: "bot_" + uuid4().hex)
    status: str = "disabled"
    webhook_url: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class BotRegistry:
    def __init__(self): self._bots: dict[str, TelegramBot] = {}
    def register(self, bot: TelegramBot) -> TelegramBot:
        if any(item.project_id == bot.project_id and item.status == "enabled" for item in self._bots.values()): raise ValueError("Project already has an enabled bot")
        self._bots[bot.id] = bot
        return bot
    def get(self, bot_id: str) -> TelegramBot | None: return self._bots.get(bot_id)
    def enable(self, bot_id: str) -> TelegramBot:
        bot = self._bots[bot_id]; bot.status = "enabled"; return bot
    def disable(self, bot_id: str) -> TelegramBot:
        bot = self._bots[bot_id]; bot.status = "disabled"; return bot
    def set_webhook(self, bot_id: str, url: str) -> TelegramBot:
        bot = self._bots[bot_id]; bot.webhook_url = url; return bot
    def list_for_project(self, project_id: str) -> list[TelegramBot]: return [b for b in self._bots.values() if b.project_id == project_id]

class CommandRegistry:
    def __init__(self): self._commands: dict[str, object] = {}
    def register(self, command: str, handler: object) -> None: self._commands[command.removeprefix("/")] = handler
    def resolve(self, command: str) -> object | None: return self._commands.get(command.removeprefix("/"))
    def names(self) -> list[str]: return sorted(self._commands)
