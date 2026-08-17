from uuid import uuid4
import inspect
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from framework.config import get_settings
from framework.core.container import ApplicationContainer
from framework.errors import FrameworkError
from framework.logging import configure_logging
from framework.observability.tracing import span
from framework.actions.base import HelpAction, StartAction
from framework.api.auth import authenticate_api_request, require_permission
from framework.api.schemas import APIKeyCreate, DatasetCreate, DeploymentCreate, DeveloperCreate, MessageCreate, ProjectCreate, TrainingCreate

settings = get_settings()
configure_logging(settings.log_level)
container = ApplicationContainer(settings)

async def authorize(request: Request, x_api_key: str | None, permission: str, project_id: str | None = None):
    record = await authenticate_api_request(request, container, x_api_key)
    require_permission(record, permission)
    if project_id is not None and record.project_id != project_id and "*" not in record.permissions:
        raise FrameworkError("API key is not authorized for this project")
    return record
container.actions.register(StartAction())
container.actions.register(HelpAction())
app = FastAPI(title=settings.app_name, version=settings.app_version)

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or request.headers.get("traceparent") or str(uuid4())
    request.state.request_id = request_id
    container.metrics.inc("framework_requests_total", method=request.method, path=request.url.path)
    with span("http.request", {"http.method": request.method, "http.path": request.url.path, "request.id": request_id}):
        response = await call_next(request)
    container.metrics.inc("framework_responses_total", method=request.method, path=request.url.path, status=str(response.status_code))
    response.headers["X-Request-ID"] = request_id
    response.headers["traceparent"] = request_id
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

@app.get("/metrics")
async def metrics(): return PlainTextResponse(container.metrics.render(), media_type="text/plain; version=0.0.4")

@app.get("/health")
async def health(): return {"success": True, "data": {"status": "healthy", "version": settings.app_version}, "error": None}

@app.get("/ready")
async def ready():
    dependencies = {"database": "not_configured", "redis": "not_configured"}
    if container.database:
        try: await container.database.ping(); dependencies["database"] = "ready"
        except Exception: dependencies["database"] = "unavailable"
    if container.redis:
        try: await container.redis.ping(); dependencies["redis"] = "ready"
        except Exception: dependencies["redis"] = "unavailable"
    status = "ready" if all(value in {"ready", "not_configured"} for value in dependencies.values()) else "not_ready"
    return {"success": status == "ready", "data": {"status": status, "dependencies": dependencies}, "error": None}

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

@app.post("/api/v1/datasets")
async def create_dataset(payload: DatasetCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "datasets.write", payload.project_id)
    if not container.dataset_repository:
        raise FrameworkError("DATABASE_URL is required for dataset persistence")
    from framework.infrastructure.sql import DatasetORM
    from framework.datasets.system import DatasetVersion, TrainingExample
    examples = [TrainingExample(text=example.text, intent=example.intent, entities=example.entities, metadata=example.metadata) for example in payload.examples]
    prepared, report = container.dataset_pipeline.prepare(DatasetVersion(uuid4().hex, payload.version, payload.project_id, tuple(examples), payload.schema_version), {example.intent for example in examples}, {entity.get("name", "") for example in examples for entity in example.entities})
    row = DatasetORM(id=prepared.dataset_id, project_id=prepared.project_id, version=prepared.version, status=prepared.status, schema_version=prepared.schema_version, examples=[example.__dict__ for example in prepared.examples])
    await container.dataset_repository.save(row)
    return {"success": True, "data": {"id": row.id, "project_id": row.project_id, "version": row.version, "status": row.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/training")
async def create_training_job(payload: TrainingCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "training.write", payload.project_id)
    if not container.training_job_repository:
        raise FrameworkError("DATABASE_URL is required for training job persistence")
    if not container.redis:
        raise FrameworkError("REDIS_URL is required to enqueue training jobs")
    from framework.infrastructure.sql import TrainingJobORM
    job = TrainingJobORM(id=uuid4().hex, project_id=payload.project_id, dataset_version=payload.dataset_version, provider="rasa", status="queued", metrics={})
    await container.training_job_repository.save(job)
    from framework.infrastructure.queue import RedisQueue
    await RedisQueue(container.redis.client).publish("training", {"job_id": job.id, "project_id": job.project_id, "dataset_version": job.dataset_version, "config_path": payload.config_path, "output_dir": payload.output_dir})
    return {"success": True, "data": {"id": job.id, "status": job.status, "provider": job.provider}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/deploy")
async def deploy_model(payload: DeploymentCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.deploy", payload.project_id)
    if not container.deployment:
        raise FrameworkError("DATABASE_URL is required for model deployment")
    result = await container.deployment.deploy(payload.project_id, payload.model_id, payload.canary)
    return {"success": True, "data": result.__dict__, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{project_id}/rollback")
async def rollback_model(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.deploy", project_id)
    if not container.deployment:
        raise FrameworkError("DATABASE_URL is required for model deployment")
    result = await container.deployment.rollback(project_id)
    return {"success": True, "data": result.__dict__, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/bots")
async def register_bot(project_id: str, payload: dict, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "bots.manage", project_id)
    from framework.channels.management import TelegramBot
    bot = container.bots.register(TelegramBot(project_id, payload["name"], payload["token_secret_ref"], metadata=payload.get("metadata", {})))
    if inspect.isawaitable(bot): bot = await bot
    return {"success": True, "data": {"id": bot.id, "project_id": bot.project_id, "name": bot.name, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/enable")
async def enable_bot(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "bots.manage")
    bot = container.bots.enable(bot_id)
    if inspect.isawaitable(bot): bot = await bot
    return {"success": True, "data": {"id": bot.id, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/disable")
async def disable_bot(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "bots.manage")
    bot = container.bots.disable(bot_id)
    if inspect.isawaitable(bot): bot = await bot
    return {"success": True, "data": {"id": bot.id, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/webhook")
async def set_bot_webhook(bot_id: str, payload: dict, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "bots.manage")
    bot = container.bots.set_webhook(bot_id, payload["url"])
    if inspect.isawaitable(bot): bot = await bot
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
    if container.redis:
        from framework.infrastructure.queue import RedisQueue
        event_id = await RedisQueue(container.redis.client).publish("telegram_updates", {"project_id": project_id, "payload": payload, "request_id": request.state.request_id})
        return {"success": True, "data": {"accepted": True, "event_id": event_id}, "error": None, "request_id": request.state.request_id}
    message = await adapter.normalize(payload, project_id=project_id)
    result = await container.engine.process_message(message)
    await adapter.send(result.response, recipient_id=message.chat_id)
    return {"success": True, "data": {"message_id": message.message_id, "intent": result.intent.name if result.intent else None, "trace": result.trace}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/messages")
async def process_message(payload: MessageCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    record = await authenticate_api_request(request, container, x_api_key)
    require_permission(record, "messages.write")
    from framework.core.models import IncomingMessage
    message = IncomingMessage(project_id=payload.project_id, channel=payload.channel, user_id=payload.user_id, chat_id=payload.chat_id or payload.user_id, text=payload.text, metadata={"permissions": sorted(record.permissions) if record else []})
    result = await container.engine.process_message(message)
    return {"success": True, "data": {"text": result.response.text, "intent": result.intent.name if result.intent else None, "confidence": result.intent.confidence if result.intent else None, "entities": [e.__dict__ if hasattr(e, "__dict__") else {"name": e.name, "value": e.value, "confidence": e.confidence} for e in result.entities], "trace": result.trace}, "error": None, "request_id": request.state.request_id}
