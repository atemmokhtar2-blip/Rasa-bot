import pytest
from framework.core.engine import FrameworkEngine
from framework.core.events import EventBus
from framework.core.models import IncomingMessage, OutgoingResponse
from framework.core.registries import ActionRegistry
from framework.core.interfaces import Action
from framework.nlu.testing import FakeNLUProvider

class AcceptanceAction(Action):
    name = 'get_order_status'
    async def execute(self, context):
        return OutgoingResponse(text='ok')

@pytest.mark.asyncio
async def test_spec02_acceptance_pipeline_events_and_idempotency():
    events = []
    bus = EventBus()
    async def collect(event): events.append(event)
    bus.subscribe('*', collect)
    actions = ActionRegistry(); actions.register(AcceptanceAction())
    engine = FrameworkEngine(FakeNLUProvider(), bus, actions)
    message = IncomingMessage(project_id='project-a', channel='test', user_id='user-a', chat_id='chat-a', channel_message_id='update-1', text='status')
    result = await engine.process_message(message)
    repeated = await engine.process_message(message)
    assert result is repeated
    assert result.success and result.response.text == 'ok'
    assert result.intent.name == 'get_order_status'
    assert result.session_id and result.request_id and result.trace_id
    for timing in ('nlu_ms', 'policy_ms', 'action_ms', 'response_ms', 'total_ms'): assert timing in result.timings
    assert {'MESSAGE_RECEIVED', 'PROJECT_RESOLVED', 'SESSION_LOADED', 'NLU_COMPLETED', 'INTENT_DETECTED', 'ENTITIES_EXTRACTED', 'POLICY_DECIDED', 'ACTION_STARTED', 'ACTION_COMPLETED', 'RESPONSE_CREATED', 'MESSAGE_PROCESSED'} <= {event.name for event in events}
