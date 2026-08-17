import pytest
from framework.core.container import ApplicationContainer
from framework.core.models import IncomingMessage

@pytest.mark.asyncio
async def test_engine_start_action_and_trace():
    container = ApplicationContainer()
    from framework.actions.base import StartAction
    container.actions.register(StartAction())
    result = await container.engine.process_message(IncomingMessage(project_id="p1", channel="test", user_id="u1", chat_id="c1", text="/start"))
    assert result.intent.name == "start"
    assert result.response.text
    assert "ACTION_COMPLETED" in result.trace

@pytest.mark.asyncio
async def test_low_confidence_fallback():
    container = ApplicationContainer()
    result = await container.engine.process_message(IncomingMessage(project_id="p1", channel="test", user_id="u1", chat_id="c1", text="unknown"))
    assert result.intent.name == "fallback"
    assert "FALLBACK" in result.trace
