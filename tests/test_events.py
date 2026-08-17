import pytest
from framework.core.events import EventBus, FrameworkEvent

@pytest.mark.asyncio
async def test_event_bus_subscription():
    bus = EventBus(); received = []
    async def handler(event): received.append(event.name)
    bus.subscribe("MESSAGE_RECEIVED", handler)
    await bus.emit(FrameworkEvent("MESSAGE_RECEIVED", {}))
    assert received == ["MESSAGE_RECEIVED"]
