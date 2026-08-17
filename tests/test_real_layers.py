import asyncio
import pytest
from framework.channels.management import BotRegistry, CommandRegistry, TelegramBot
from framework.channels.webhooks import TelegramWebhookVerifier
from framework.core.models import Entity, IntentPrediction
from framework.datasets.pipeline import DatasetPipeline
from framework.datasets.system import DatasetVersion, TrainingExample
from framework.models.evaluation import EvaluationEngine
from framework.plugins.runtime import PluginRuntime
from framework.errors import AuthorizationError, PluginError


def test_dataset_pipeline_normalizes_deduplicates_and_validates():
    example = TrainingExample('  hello   world ', ' greet ')
    dataset = DatasetVersion('d2', 'v1', 'p1', (example, example))
    prepared, report = DatasetPipeline().prepare(dataset, {'greet'}, set())
    assert prepared.status == 'validated'
    assert len(prepared.examples) == 1
    assert report.duplicate_count == 1


def test_evaluation_metrics_are_real_calculations():
    result = EvaluationEngine().evaluate('m1', 'v1', [{
        'prediction': IntentPrediction('greet', .9), 'expected_intent': 'greet',
        'entities': [Entity('name', 'Ali')], 'expected_entities': {'name': 'Ali'}, 'action_success': True,
    }, {
        'prediction': IntentPrediction('fallback', .2), 'expected_intent': 'greet',
        'entities': [], 'expected_entities': {}, 'action_success': False,
    }])
    assert result.intent_accuracy == .5
    assert result.entity_accuracy == 1.0
    assert result.fallback_rate == .5
    assert result.action_success_rate == .5

@pytest.mark.asyncio
async def test_plugin_runtime_enforces_permissions_and_timeout():
    runtime = PluginRuntime(timeout_seconds=.01)
    async def operation(): return 'ok'
    assert await runtime.execute('p', operation, {'http.request'}, {'http.request'}) == 'ok'
    with pytest.raises(AuthorizationError): await runtime.execute('p', operation, set(), {'http.request'})
    async def slow(): await asyncio.sleep(.1)
    with pytest.raises(PluginError): await runtime.execute('p', slow, set(), set())


def test_bot_registry_and_webhook_verifier():
    bots = BotRegistry(); bot = bots.register(TelegramBot('p1', 'bot', 'secret-ref'))
    assert bots.enable(bot.id).status == 'enabled'
    assert bots.set_webhook(bot.id, 'https://example.test/hook').webhook_url.startswith('https://')
    assert TelegramWebhookVerifier('secret').verify('secret')
    assert not TelegramWebhookVerifier('secret').verify('wrong')
    commands = CommandRegistry(); commands.register('/start', object())
    assert commands.resolve('start') is not None


@pytest.mark.asyncio
async def test_tool_execution_requires_declared_permissions():
    from framework.core.integrations import ToolExecutionService
    class Tool:
        name = 'http'
        required_permissions = {'http.request'}
        async def execute(self, **kwargs): return kwargs['url']
    service = ToolExecutionService()
    assert await service.execute(Tool(), {'http.request'}, url='https://example.test') == 'https://example.test'
    with pytest.raises(AuthorizationError): await service.execute(Tool(), set(), url='https://example.test')


def test_webhook_signature_is_deterministic():
    from framework.core.integrations import WebhookRegistry
    signature = WebhookRegistry.signature('secret', b'payload')
    assert signature == WebhookRegistry.signature('secret', b'payload')
    assert signature != WebhookRegistry.signature('other', b'payload')
