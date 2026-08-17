from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from framework.config import get_settings
from framework.core.container import ApplicationContainer
from framework.errors import FrameworkError
from framework.logging import configure_logging
from framework.actions.base import HelpAction, StartAction

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

@app.exception_handler(FrameworkError)
async def framework_error_handler(request: Request, exc: FrameworkError):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "data": None, "error": {"code": exc.code, "message": exc.message}, "request_id": getattr(request.state, "request_id", None)})

@app.get("/health")
async def health(): return {"success": True, "data": {"status": "healthy", "version": settings.app_version}, "error": None}

@app.get("/ready")
async def ready(): return {"success": True, "data": {"status": "ready", "dependencies": {"database": "configured"}}, "error": None}

@app.post("/api/v1/developers")
async def create_developer(payload: dict, request: Request):
    developer = await container.developers.create_developer(payload["name"], payload["email"])
    return {"success": True, "data": {"id": developer.id, "name": developer.name, "email": developer.email}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects")
async def create_project(payload: dict, request: Request):
    project = await container.developers.create_project(payload["owner_id"], payload["name"], payload.get("description", ""), payload.get("environment", "development"))
    return {"success": True, "data": {"id": project.id, "name": project.name, "owner_id": project.owner_id, "environment": project.environment, "status": project.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys")
async def create_api_key(payload: dict, request: Request):
    created = await container.developers.create_api_key(payload["developer_id"], payload["project_id"], payload.get("environment", "development"), set(payload.get("permissions", [])))
    return {"success": True, "data": {"key_id": created.key_id, "secret": created.secret, "project_id": created.project_id, "environment": created.environment}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/webhooks/telegram/{project_id}")
async def telegram_webhook(project_id: str, payload: dict, request: Request):
    from framework.channels.telegram import TelegramAdapter
    adapter = TelegramAdapter(settings.telegram_bot_token)
    message = await adapter.normalize(payload, project_id=project_id)
    result = await container.engine.process_message(message)
    await adapter.send(result.response, recipient_id=message.chat_id)
    return {"success": True, "data": {"message_id": message.message_id, "intent": result.intent.name if result.intent else None, "trace": result.trace}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/messages")
async def process_message(payload: dict, request: Request):
    from framework.core.models import IncomingMessage
    message = IncomingMessage(project_id=payload["project_id"], channel=payload.get("channel", "api"), user_id=str(payload["user_id"]), chat_id=str(payload.get("chat_id", payload["user_id"])), text=payload.get("text"))
    result = await container.engine.process_message(message)
    return {"success": True, "data": {"text": result.response.text, "intent": result.intent.name if result.intent else None, "confidence": result.intent.confidence if result.intent else None, "entities": [e.__dict__ if hasattr(e, "__dict__") else {"name": e.name, "value": e.value, "confidence": e.confidence} for e in result.entities], "trace": result.trace}, "error": None, "request_id": request.state.request_id}
