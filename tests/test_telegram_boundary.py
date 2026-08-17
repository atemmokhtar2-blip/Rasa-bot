import pytest
from framework.channels.telegram import TelegramAdapter

@pytest.mark.asyncio
async def test_telegram_normalization_is_channel_specific():
    message = await TelegramAdapter().normalize({"update_id": 1, "message": {"message_id": 7, "text": "hello", "from": {"id": 9}, "chat": {"id": 10}}}, project_id="project-a")
    assert message.channel == "telegram"
    assert message.user_id == "9"
    assert message.chat_id == "10"
    assert message.text == "hello"
