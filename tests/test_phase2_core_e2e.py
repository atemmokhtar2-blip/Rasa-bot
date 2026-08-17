import pytest
from framework.core.engine import FrameworkEngine
from framework.core.events import EventBus
from framework.core.models import IncomingMessage, OutgoingResponse
from framework.core.registries import ActionRegistry
from framework.core.interfaces import Action
from framework.nlu.testing import FakeNLUProvider

class EchoAction(Action):
    name = "get_order_status"
    async def execute(self, context):
        return OutgoingResponse(text=f"intent={context['intent'].name}")

@pytest.mark.asyncio
async def test_phase2_core_e2e_without_external_services():
    actions = ActionRegistry(); actions.register(EchoAction())
    engine = FrameworkEngine(FakeNLUProvider(), EventBus(), actions)
    result = await engine.process_message(IncomingMessage(project_id="p1", channel="test", user_id="u1", chat_id="c1", text="عايز أعرف حالة الطلب"))
    assert result.success is True
    assert result.intent.name == "get_order_status"
    assert result.response.text == "intent=get_order_status"
    assert result.session_id
    assert result.timings["nlu_ms"] >= 0
    assert result.trace_id
