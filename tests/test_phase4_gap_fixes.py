import asyncio
from types import SimpleNamespace
from framework.observability.quota import QuotaService
from framework.core.integrations import QueuedWebhookDispatcher, WebhookSubscription
from framework.channels.management import TelegramBot

class FakeUsage:
    def __init__(self, totals=None, windows=None): self._totals = totals or {}; self._windows = windows or {}
    async def totals(self, project_id): return dict(self._totals)
    async def window_totals(self, project_id, *, since): return dict(self._windows)

class FakeQueue:
    def __init__(self): self.calls=[]
    async def publish(self, topic, payload): self.calls.append((topic, payload)); return "event-1"

def test_quota_enforcement_and_dashboard_windows():
    async def scenario():
        usage = FakeUsage(totals={"api_request": 10, "training_job": 1}, windows={"api_request": 10})
        project = SimpleNamespace(configuration={"quotas": {"daily_requests": 10, "monthly_requests": 20, "training_jobs": 2}})
        async def load_project(_): return project
        quotas = QuotaService(usage, load_project)
        snapshot = await quotas.snapshot("project-a")
        assert snapshot["windows"]["daily"]["api_request"] == 10
        assert snapshot["limits"]["daily_requests"] == 10
        try:
            await quotas.enforce_request("project-a")
        except Exception as exc:
            assert exc.code == "RATE_LIMIT_EXCEEDED"
        else:
            raise AssertionError("daily quota must be enforced")
    asyncio.run(scenario())

def test_webhook_queue_contains_project_and_webhook_identity():
    async def scenario():
        queue = FakeQueue()
        dispatcher = QueuedWebhookDispatcher(queue)
        sub = WebhookSubscription("message.processed", "https://example.test/hook", "secret", metadata={"webhook_id": "wh-1", "project_id": "project-a"})
        await dispatcher.enqueue(sub, {"event_id": "evt-1", "project_id": "project-a", "payload": {"ok": True}})
        topic, payload = queue.calls[0]
        assert topic == "webhooks"
        assert payload["webhook_id"] == "wh-1"
        assert payload["project_id"] == "project-a"
        assert payload["event_id"] == "evt-1"
    asyncio.run(scenario())

def test_telegram_bot_has_non_plaintext_secret_reference_contract():
    bot = TelegramBot("project-a", "bot", "telegram/project-a/bot", webhook_secret_ref="telegram-webhook/project-a/bot")
    assert bot.webhook_secret_ref.startswith("telegram-webhook/")
    assert not hasattr(bot, "token")
