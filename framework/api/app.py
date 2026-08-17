from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from framework.config import get_settings
from framework.core.container import ApplicationContainer
from framework.errors import FrameworkError
from framework.logging import configure_logging
from framework.actions.base import HelpAction, StartAction
from framework.api.auth import authenticate_api_request, require_permission
from framework.api.schemas import APIKeyCreate, DeveloperCreate, MessageCreate, ProjectCreate

settings = get_settings()
configure_logging(settings.log_level)
container = ApplicationContainer(settings)
container.actions.register(StartAction())
container.actions.register(HelpAction())
app = FastAPI(title=settings.app_name, version=settings.app_version)

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"success": False, "data": None, "error": {"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": exc.errors()}, "request_id": getattr(request.state, "request_id", None)})

@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "data": None, "error": {"code": "HTTP_ERROR", "message": str(exc.detail)}, "request_id": getattr(request.state, "request_id", None)})

@app.exception_handler(FrameworkError)
async def framework_error_handler(request: Request, exc: FrameworkError):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "data": None, "error": {"code": exc.code, "message": exc.message}, "request_id": getattr(request.state, "request_id", None)})

@app.get("/health")
async def health(): return {"success": True, "data": {"status": "healthy", "version": settings.app_version}, "error": None}

@app.get("/ready")
async def ready(): return {"success": True, "data": {"status": "ready", "dependencies": {"database": "configured"}}, "error": None}

@app.post("/api/v1/developers")
async def create_developer(payload: DeveloperCreate, request: Request):
    developer = await container.developers.create_developer(payload.name, str(payload.email))
    return {"success": True, "data": {"id": developer.id, "name": developer.name, "email": developer.email}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects")
async def create_project(payload: ProjectCreate, request: Request):
    project = await container.developers.create_project(payload.owner_id, payload.name, payload.description, payload.environment)
    return {"success": True, "data": {"id": project.id, "name": project.name, "owner_id": project.owner_id, "environment": project.environment, "status": project.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys")
async def create_api_key(payload: APIKeyCreate, request: Request):
    created = await container.developers.create_api_key(payload.developer_id, payload.project_id, payload.environment, payload.permissions)
    return {"success": True, "data": {"key_id": created.key_id, "secret": created.secret, "project_id": created.project_id, "environment": created.environment}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/bots")
async def register_bot(project_id: str, payload: dict, request: Request):
    from framework.channels.management import TelegramBot
    bot = container.bots.register(TelegramBot(project_id, payload["name"], payload["token_secret_ref"], metadata=payload.get("metadata", {})))
    return {"success": True, "data": {"id": bot.id, "project_id": bot.project_id, "name": bot.name, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/enable")
async def enable_bot(bot_id: str, request: Request):
    bot = container.bots.enable(bot_id)
    return {"success": True, "data": {"id": bot.id, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/disable")
async def disable_bot(bot_id: str, request: Request):
    bot = container.bots.disable(bot_id)
    return {"success": True, "data": {"id": bot.id, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/webhook")
async def set_bot_webhook(bot_id: str, payload: dict, request: Request):
    bot = container.bots.set_webhook(bot_id, payload["url"])
    return {"success": True, "data": {"id": bot.id, "webhook_url": bot.webhook_url}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/api-keys")
async def list_api_keys(project_id: str, request: Request):
    keys = await container.developers.list_api_keys(project_id)
    data = [{"key_id": key.key_id, "project_id": key.project_id, "environment": key.environment, "permissions": sorted(key.permissions), "status": key.status, "created_at": key.created_at.isoformat()} for key in keys]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, request: Request):
    created = await container.developers.rotate_api_key(key_id)
    return {"success": True, "data": {"key_id": created.key_id, "secret": created.secret, "project_id": created.project_id, "environment": created.environment}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys/{key_id}/disable")
async def disable_api_key(key_id: str, request: Request):
    await container.developers.disable_api_key(key_id)
    return {"success": True, "data": {"key_id": key_id, "status": "disabled"}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys/{key_id}/expire")
async def expire_api_key(key_id: str, request: Request):
    await container.developers.expire_api_key(key_id)
    return {"success": True, "data": {"key_id": key_id, "status": "expired"}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/webhooks/telegram/{project_id}")
async def telegram_webhook(project_id: str, payload: dict, request: Request):
    from framework.channels.telegram import TelegramAdapter
    from framework.channels.webhooks import TelegramWebhookVerifier
    verifier = TelegramWebhookVerifier(settings.telegram_webhook_secret)
    if not verifier.verify(request.headers.get("X-Telegram-Bot-Api-Secret-Token")):
        from framework.errors import AuthenticationError
        raise AuthenticationError("Invalid Telegram webhook secret")
    adapter = TelegramAdapter(settings.telegram_bot_token)
    message = await adapter.normalize(payload, project_id=project_id)
    result = await container.engine.process_message(message)
    await adapter.send(result.response, recipient_id=message.chat_id)
    return {"success": True, "data": {"message_id": message.message_id, "intent": result.intent.name if result.intent else None, "trace": result.trace}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/messages")
async def process_message(payload: MessageCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    record = await authenticate_api_request(request, container, x_api_key)
    require_permission(record, "messages.write")
    from framework.core.models import IncomingMessage
    message = IncomingMessage(project_id=payload.project_id, channel=payload.channel, user_id=payload.user_id, chat_id=payload.chat_id or payload.user_id, text=payload.text)
    result = await container.engine.process_message(message)
    return {"success": True, "data": {"text": result.response.text, "intent": result.intent.name if result.intent else None, "confidence": result.intent.confidence if result.intent else None, "entities": [e.__dict__ if hasattr(e, "__dict__") else {"name": e.name, "value": e.value, "confidence": e.confidence} for e in result.entities], "trace": result.trace}, "error": None, "request_id": request.state.request_id}
