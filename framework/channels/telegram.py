from typing import Any
import httpx
from framework.core.interfaces import ChannelAdapter
from framework.core.models import IncomingMessage, OutgoingResponse
from framework.errors import TransportError

class TelegramAdapter(ChannelAdapter):
    """Transport-only adapter: normalization and Bot API delivery, never business logic."""
    channel = "telegram"

    def __init__(self, token: str | None = None, timeout: float = 10.0):
        self.token = token
        self.timeout = timeout

    async def normalize(self, payload: dict[str, Any], *, project_id: str) -> IncomingMessage:
        message = payload.get("message", payload)
        sender = message.get("from", {})
        chat = message.get("chat", {})
        return IncomingMessage(
            project_id=project_id,
            channel=self.channel,
            user_id=str(sender.get("id", "unknown")),
            chat_id=str(chat.get("id", "unknown")),
            text=message.get("text"),
            channel_message_id=str(message.get("message_id", "")),
            reply_to=str(message.get("reply_to_message", {}).get("message_id")) if message.get("reply_to_message") else None,
            metadata={"telegram": {"update_id": payload.get("update_id"), "raw_message_type": list(message.keys())}},
        )

    async def send(self, response: OutgoingResponse, *, recipient_id: str) -> dict[str, Any]:
        messages = response.rendered_messages()
        if not self.token:
            return {"recipient_id": recipient_id, "messages": messages, "mode": "dry-run"}
        results = []
        for text in messages:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    api_response = await client.post(
                        f"https://api.telegram.org/bot{self.token}/sendMessage",
                        json={"chat_id": recipient_id, "text": text, "parse_mode": response.parse_mode},
                    )
                    api_response.raise_for_status()
                    body = api_response.json()
                    if not body.get("ok"):
                        raise TransportError("Telegram rejected sendMessage")
                    results.append(body.get("result"))
            except TransportError:
                raise
            except Exception as exc:
                raise TransportError("Telegram API request failed") from exc
        return {"recipient_id": recipient_id, "results": results}

    async def set_webhook(self, url: str) -> dict[str, Any]:
        if not self.token:
            raise TransportError("Telegram token is not configured")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"https://api.telegram.org/bot{self.token}/setWebhook", json={"url": url})
                response.raise_for_status()
                body = response.json()
                if not body.get("ok"):
                    raise TransportError("Telegram rejected setWebhook")
                return body
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError("Telegram webhook registration failed") from exc
