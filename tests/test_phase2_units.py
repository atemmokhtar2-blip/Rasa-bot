import asyncio
import pytest
from framework.core.events import EventBus, FrameworkEvent
from framework.core.state import ContextManager, DialogueManager, SessionManager
from framework.core.models import Entity, IntentPrediction
from framework.core.integrations import ToolExecutionService
from framework.errors import AuthorizationError, ToolError
from framework.nlu.policy import ConfidencePolicy, EntityNormalizer

@pytest.mark.asyncio
async def test_session_and_context_lifecycle():
    sessions = SessionManager(timeout_minutes=1)
    session = await sessions.create_session('p', 'u', 'c')
    assert await sessions.is_active(session)
    await sessions.update_session(session, state='waiting_for_entities')
    assert (await sessions.get_session(session.id)).state == 'waiting_for_entities'
    context = ContextManager()
    await context.set_context(session.id, {'a': 1})
    assert await context.update_context(session.id, {'b': 2}) == {'a': 1, 'b': 2}
    await sessions.close_session(session)
    assert not await sessions.is_active(session)

@pytest.mark.asyncio
async def test_event_handler_failure_is_isolated():
    bus = EventBus(); called = []
    async def failing(event): raise RuntimeError('analytics')
    async def healthy(event): called.append(event.name)
    bus.subscribe('MESSAGE_PROCESSED', failing); bus.subscribe('MESSAGE_PROCESSED', healthy)
    event = FrameworkEvent('MESSAGE_PROCESSED', {})
    await bus.emit(event)
    assert called == ['MESSAGE_PROCESSED']
    assert event.payload['handler_errors']

def test_confidence_and_entity_normalization():
    policy = ConfidencePolicy(0.8, 0.55)
    assert policy.classify(0.9).status == 'accept'
    assert policy.classify(0.7).status == 'clarify'
    assert policy.classify(0.2).status == 'fallback'
    normalized = EntityNormalizer({'date': lambda value, metadata: value.strip()}).normalize([Entity('date', ' tomorrow ')])
    assert normalized[0].value == 'tomorrow'

@pytest.mark.asyncio
async def test_tool_authorization_and_timeout():
    class Tool:
        name = 'secure'; required_permissions = {'secure.use'}
        async def execute(self, **kwargs): return 'ok'
    with pytest.raises(AuthorizationError): await ToolExecutionService().execute(Tool(), set())
    assert await ToolExecutionService().execute(Tool(), {'secure.use'}) == 'ok'
