# Specification 04 Quick Start

## API and Python SDK

Create a project and an API key through the versioned API. The API key secret is returned only during creation; subsequent list operations return metadata and prefix only.

```python
from framework import Client

client = Client(api_key="adf_live_...", base_url="http://localhost:8000")
response = client.messages.create(
    text="عايز أعرف حالة الطلب",
    project_id="project_id",
    user_id="customer-123",
    session_id="session_123",
    metadata={"customer_id": "123"},
)
print(response.text, response.intent, response.request_id)
```

`AsyncClient` exposes the same message contract for async applications. Safe retries are enabled only for reads or requests carrying an explicit `Idempotency-Key`.

## Telegram

Register a Telegram bot with `POST /api/v1/projects/{project_id}/bots` and provide its token over TLS. The token is validated with Telegram `getMe`, stored through the secret abstraction, and never returned in bot list/status responses. Connect it with the enable endpoint, choose the project/environment model, and send updates to the Telegram webhook endpoint or run the Redis-backed Telegram worker.

## Webhooks

Create a webhook with a URL and event list. The response contains the signing secret once. Deliveries include `X-Framework-Signature` (HMAC-SHA256) and `X-Framework-Event-ID`; failed requests are retried at most three times and then moved to the dead-letter queue.

## API Errors

All errors use the envelope `{success: false, data: null, error: {...}, request_id}`. Authentication, authorization, validation, not-found, conflict, rate-limit, and internal failures map to HTTP 401, 403, 422, 404, 409, 429, and 500 respectively.
