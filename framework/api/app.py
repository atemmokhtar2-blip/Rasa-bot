from uuid import uuid4
from dataclasses import asdict
from datetime import datetime, timezone
import inspect
import secrets
from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from framework.config import get_settings
from framework.core.container import ApplicationContainer
from framework.errors import AuthorizationError, FrameworkError, NotFoundError
from framework.logging import configure_logging
from framework.observability import AuditEvent
from framework.observability.tracing import span
from framework.actions.base import HelpAction, StartAction
from framework.api.auth import authenticate_api_request, require_permission
from framework.api.schemas import APIKeyCreate, CandidateCreate, CandidateTransition, ConflictResolve, DatasetCreate, DatasetValidateRequest, DatasetVersionCreate, DeploymentCreate, DeveloperCreate, FeedbackCreate, InteractionCollect, MessageCreate, ModelComparisonRequest, ModelDeploymentRequest, ModelEvaluationCreate, ModelHealthUpdate, ModelRuntimeServeRequest, ModelVersionCreate, ProjectCreate, ProjectUpdate, ReviewCreate, ThresholdOptimizationRequest, TrainingCreate
from framework.learning.continuous import CandidateStatus, SampleStatus
from framework.learning.review import ReviewDecision
from framework.learning.policy import FeedbackType

settings = get_settings()
configure_logging(settings.log_level)
container = ApplicationContainer(settings)

def serialize_training_example(example):
    data = asdict(example)
    data["entities"] = list(example.entities)
    data["review_status"] = example.review_status.value if hasattr(example.review_status, "value") else str(example.review_status)
    data["reviewed_at"] = example.reviewed_at.isoformat() if example.reviewed_at else None
    return data

async def authorize(request: Request, x_api_key: str | None, permission: str, project_id: str | None = None):
    record = await authenticate_api_request(request, container, x_api_key)
    require_permission(record, permission)
    if record is not None and project_id is not None and record.project_id != project_id and "*" not in record.permissions:
        raise AuthorizationError("API key is not authorized for this project")
    return record

async def authorize_any(request: Request, x_api_key: str | None, permissions: tuple[str, ...], project_id: str | None = None):
    record = await authenticate_api_request(request, container, x_api_key)
    if record is None: return None
    if not any(permission in record.permissions or "*" in record.permissions for permission in permissions): raise AuthorizationError(f"Missing one of permissions: {permissions}")
    if project_id is not None and record.project_id != project_id and "*" not in record.permissions: raise AuthorizationError("API key is not authorized for this project")
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
    return JSONResponse(status_code=exc.status_code, content={"success": False, "data": None, "error": {"code": exc.code, "message": exc.message, "details": exc.details}, "request_id": getattr(request.state, "request_id", None)})

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    container.metrics.inc("framework_errors_total", code="INTERNAL_ERROR", path=request.url.path)
    return JSONResponse(status_code=500, content={"success": False, "data": None, "error": {"code": "INTERNAL_ERROR", "message": "Internal server error", "details": {}}, "request_id": getattr(request.state, "request_id", None)})

@app.get("/api/v1/projects/{project_id}/usage")
async def project_usage(project_id: str, request: Request, limit: int = 100, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "usage.read", project_id)
    events = await container.usage.list_events(project_id, limit)
    return {"success": True, "data": {"totals": await container.usage.totals(project_id), "events": [{"id": event.id, "metric": event.metric, "quantity": event.quantity, "request_id": event.request_id, "metadata": event.metadata, "created_at": event.created_at.isoformat()} for event in events]}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/quota")
async def project_quota(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "usage.read", project_id)
    return {"success": True, "data": await container.quotas.snapshot(project_id), "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/audit-logs")
async def project_audit_logs(project_id: str, request: Request, limit: int = 100, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "audit.read", project_id)
    events = await container.audit.list_project(project_id, limit)
    data = [{"id": event.id, "event_name": event.event_name, "actor_id": event.actor_id, "project_id": event.project_id, "changes": event.changes, "created_at": event.created_at.isoformat()} for event in events]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/audit-logs/export")
async def export_project_audit(project_id: str, request: Request, limit: int = 1000, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "audit.read", project_id)
    body = await container.audit.export_project(project_id, limit)
    return PlainTextResponse(body, media_type="application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="audit-{project_id}.ndjson"', "X-Request-ID": request.state.request_id})

@app.get("/metrics")
async def metrics(): return PlainTextResponse(container.metrics.render(), media_type="text/plain; version=0.0.4")

@app.on_event("startup")
async def framework_startup():
    await container.startup()
    if not container.plugin_loader.loaded:
        await container.extensions.load("framework.extensions.first_party.telegram_utilities", environment=settings.app_env)

@app.on_event("shutdown")
async def framework_shutdown():
    for plugin in list(container.plugin_loader.list()):
        try: await container.extensions.unload(plugin.manifest.plugin_id)
        except Exception: pass
    await container.shutdown()

@app.get("/health")
async def health(): return {"success": True, "data": {"status": "healthy", "version": settings.app_version}, "error": None}

@app.get("/health/extensions")
async def extensions_health():
    return {"success": True, "data": {"plugins": container.plugin_loader.health(), "providers": [{"name": getattr(provider, "name", provider.__class__.__name__), "version": getattr(provider, "version", settings.app_version), "type": getattr(provider, "provider_type", "provider")} for provider in container.providers.list()]}, "error": None}

@app.get("/api/v1/projects/{project_id}/extensions")
async def project_extensions(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "extensions.read", project_id)
    return {"success": True, "data": {"project_id": project_id, "plugins": [item for item in container.plugin_loader.health() if item.get("project_id") in {None, project_id}], "actions": [{"name": item.name, "version": getattr(item, "version", "1.0.0"), "scope": getattr(item, "scope", "global")} for item in container.actions.list(project_id=project_id)], "tools": [{"name": item.name, "version": getattr(item, "version", "1.0.0"), "scope": getattr(item, "scope", "global")} for item in container.tools.list(project_id=project_id)], "providers": [{"name": getattr(item, "name", item.__class__.__name__), "version": getattr(item, "version", "1.0.0"), "type": getattr(item, "provider_type", "provider")} for item in container.providers.list(project_id=project_id)]}, "error": None, "request_id": request.state.request_id}

@app.get("/ready")
async def ready():
    dependencies = {"database": "not_configured", "redis": "not_configured", "object_storage": "not_configured", "secret_manager": "not_configured", "nlu": "not_configured", "telegram": "not_configured"}
    if container.database:
        try: await container.database.ping(); dependencies["database"] = "ready"
        except Exception: dependencies["database"] = "unavailable"
    if container.redis:
        try: await container.redis.ping(); dependencies["redis"] = "ready"
        except Exception: dependencies["redis"] = "unavailable"
    if container.object_storage:
        try: await container.object_storage.ping(); dependencies["object_storage"] = "ready"
        except Exception: dependencies["object_storage"] = "unavailable"
    if hasattr(container.secrets, "ping"):
        try: await container.secrets.ping(); dependencies["secret_manager"] = "ready"
        except Exception: dependencies["secret_manager"] = "unavailable"
    try:
        nlu_health = await container.nlu.health(); dependencies["nlu"] = nlu_health.get("status", "unavailable")
    except Exception: dependencies["nlu"] = "unavailable"
    try:
        telegram_health = await TelegramAdapter(settings.telegram_bot_token).health(); dependencies["telegram"] = telegram_health.get("status", "unavailable")
        if settings.app_env not in {"production", "staging"} and dependencies["telegram"] == "unavailable": dependencies["telegram"] = "not_configured"
    except Exception: dependencies["telegram"] = "not_configured" if settings.app_env not in {"production", "staging"} else "unavailable"
    status = "ready" if all(value in {"ready", "not_configured"} for value in dependencies.values()) else "not_ready"
    return {"success": status == "ready", "data": {"status": status, "dependencies": dependencies}, "error": None}

@app.post("/api/v1/developers")
async def create_developer(payload: DeveloperCreate, request: Request):
    developer = await container.developers.create_developer(payload.name, str(payload.email))
    return {"success": True, "data": {"id": developer.id, "name": developer.name, "email": developer.email}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/developers")
async def list_developers(request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "developers.read")
    rows = await container.developers.list_developers()
    data = [{"id": row.id, "name": row.name, "email": row.email, "created_at": row.created_at.isoformat()} for row in rows]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/developers/{developer_id}")
async def get_developer(developer_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "developers.read")
    row = await container.developers.get_developer(developer_id)
    return {"success": True, "data": {"id": row.id, "name": row.name, "email": row.email, "created_at": row.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects")
async def create_project(payload: ProjectCreate, request: Request):
    project = await container.developers.create_project(payload.owner_id, payload.name, payload.description, payload.environment)
    return {"success": True, "data": {"id": project.id, "name": project.name, "owner_id": project.owner_id, "environment": project.environment, "status": project.status, "configuration": getattr(project, "configuration", {})}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects")
async def list_projects(request: Request, owner_id: str | None = None, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    record = await authorize(request, x_api_key, "projects.read")
    if record is not None and "*" not in record.permissions:
        rows = [await container.developers.get_project(record.project_id)]
    else:
        rows = await container.developers.list_projects(owner_id)
    data = [{"id": row.id, "name": row.name, "owner_id": row.owner_id, "description": row.description, "environment": row.environment, "status": row.status, "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(), "configuration": getattr(row, "configuration", {})} for row in rows]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "projects.read", project_id)
    row = await container.developers.get_project(project_id)
    return {"success": True, "data": {"id": row.id, "name": row.name, "owner_id": row.owner_id, "description": row.description, "environment": row.environment, "status": row.status, "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(), "configuration": getattr(row, "configuration", {})}, "error": None, "request_id": request.state.request_id}

@app.patch("/api/v1/projects/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "projects.write", project_id)
    row = await container.developers.update_project(project_id, **payload.model_dump(exclude_none=True))
    return {"success": True, "data": {"id": row.id, "name": row.name, "owner_id": row.owner_id, "description": row.description, "environment": row.environment, "status": row.status, "updated_at": row.updated_at.isoformat(), "configuration": getattr(row, "configuration", {})}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys")
async def create_api_key(payload: APIKeyCreate, request: Request):
    created = await container.developers.create_api_key(payload.developer_id, payload.project_id, payload.environment, payload.permissions, name=payload.name, key_type=payload.key_type, expires_at=payload.expires_at, metadata=payload.metadata)
    await container.audit.record(AuditEvent("API_KEY_CREATED", actor_id=payload.developer_id, project_id=payload.project_id, changes={"key_id": created.key_id, "prefix": created.prefix, "environment": created.environment, "key_type": created.key_type, "permissions": sorted(payload.permissions)}))
    return {"success": True, "data": {"key_id": created.key_id, "secret": created.secret, "prefix": created.prefix, "project_id": created.project_id, "environment": created.environment, "key_type": created.key_type}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/feedback")
async def create_feedback(payload: FeedbackCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.write", payload.project_id)
    item = container.feedback.record(project_id=payload.project_id, interaction_id=payload.interaction_id, feedback_type=FeedbackType(payload.type), intent=payload.intent, entities=tuple(payload.entities), source=payload.source, trusted=payload.trusted)
    await container.audit.record(AuditEvent("LEARNING_FEEDBACK_RECORDED", project_id=payload.project_id, changes={"feedback_id": item.feedback_id, "interaction_id": item.interaction_id, "type": item.feedback_type.value, "trusted": item.trusted}))
    return {"success": True, "data": {**item.__dict__, "feedback_type": item.feedback_type.value, "created_at": item.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/feedback")
async def list_feedback(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.read", project_id)
    return {"success": True, "data": [{**item.__dict__, "feedback_type": item.feedback_type.value, "created_at": item.created_at.isoformat()} for item in container.feedback.list_project(project_id)], "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/learning/interactions")
async def collect_learning_interaction(payload: InteractionCollect, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize_any(request, x_api_key, ("learning.write", "messages.write"), payload.project_id)
    record = container.learning.collect(project_id=payload.project_id, session_id=payload.session_id, language=payload.language, input_text=payload.input, predicted_intent=payload.predicted_intent, confidence=payload.confidence, entities=payload.entities, response=payload.response, model_version=payload.model_version, processing_time_ms=payload.processing_time, status=payload.status, metadata=payload.metadata)
    await container.audit.record(AuditEvent("LEARNING_INTERACTION_COLLECTED", project_id=payload.project_id, changes={"interaction_id": record.interaction_id, "model_version": payload.model_version, "status": payload.status}))
    return {"success": True, "data": record.to_dict(), "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/learning/candidates")
async def create_learning_candidate(payload: CandidateCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.write", payload.project_id)
    candidate = container.learning.candidate_from_interaction(payload.interaction_id, project_id=payload.project_id, suggested_intent=payload.suggested_intent, context=payload.context, quality_score=payload.quality_score)
    return {"success": True, "data": {**candidate.__dict__, "status": candidate.status.value, "sample_status": candidate.sample_status.value, "created_at": candidate.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/learning/candidates")
async def list_learning_candidates(project_id: str, request: Request, status: str | None = None, sample_status: str | None = None, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.read", project_id)
    candidate_status = CandidateStatus(status) if status else None
    lifecycle_status = SampleStatus(sample_status) if sample_status else None
    rows = container.learning.list_candidates(project_id, status=candidate_status, sample_status=lifecycle_status)
    data = [{**row.__dict__, "status": row.status.value, "sample_status": row.sample_status.value, "created_at": row.created_at.isoformat()} for row in rows]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/learning/candidates/{sample_id}/transition")
async def transition_learning_candidate(sample_id: str, payload: CandidateTransition, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.review", payload.project_id)
    candidate = container.learning.transition_candidate(sample_id, project_id=payload.project_id, status=CandidateStatus(payload.status), sample_status=SampleStatus(payload.sample_status))
    await container.audit.record(AuditEvent("LEARNING_CANDIDATE_TRANSITIONED", project_id=payload.project_id, changes={"sample_id": sample_id, "status": payload.status, "sample_status": payload.sample_status}))
    return {"success": True, "data": {**candidate.__dict__, "status": candidate.status.value, "sample_status": candidate.sample_status.value, "created_at": candidate.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/learning/reviews")
async def create_learning_review(payload: ReviewCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.review", payload.project_id)
    review = container.reviews.review(project_id=payload.project_id, sample_id=payload.sample_id, reviewer_id=payload.reviewer_id, decision=ReviewDecision(payload.decision), corrected_intent=payload.corrected_intent, corrected_entities=tuple(payload.corrected_entities), notes=payload.notes, context=payload.context)
    await container.audit.record(AuditEvent("LEARNING_REVIEW_CREATED", actor_id=payload.reviewer_id, project_id=payload.project_id, changes={"review_id": review.review_id, "sample_id": review.sample_id, "decision": review.decision.value, "annotation_version": review.annotation_version}))
    if review.decision in {ReviewDecision.APPROVE, ReviewDecision.CORRECT}:
        candidate_status = CandidateStatus.APPROVED
        sample_status = SampleStatus.APPROVED
        try: container.learning.transition_candidate(payload.sample_id, project_id=payload.project_id, status=candidate_status, sample_status=sample_status)
        except KeyError: pass
    return {"success": True, "data": {**review.__dict__, "decision": review.decision.value, "created_at": review.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/learning/conflicts")
async def list_learning_conflicts(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.review", project_id)
    return {"success": True, "data": [item.__dict__ for item in container.reviews.list_conflicts(project_id)], "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/learning/conflicts/{conflict_id}/resolve")
async def resolve_learning_conflict(conflict_id: str, payload: ConflictResolve, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "learning.review", payload.project_id)
    conflict = container.reviews.resolve(conflict_id, project_id=payload.project_id, resolver_id=payload.resolver_id, intent=payload.intent, policy=payload.policy)
    await container.audit.record(AuditEvent("LEARNING_CONFLICT_RESOLVED", actor_id=payload.resolver_id, project_id=payload.project_id, changes={"conflict_id": conflict_id, "intent": payload.intent, "policy": payload.policy}))
    return {"success": True, "data": conflict.__dict__, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/datasets")
async def create_dataset(payload: DatasetCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "datasets.write", payload.project_id)
    if not container.dataset_repository or not container.dataset_catalog_repository:
        from framework.datasets.system import ReviewStatus, TrainingExample
        dataset = next((item for item in container.datasets.list_project(payload.project_id) if item.name == (payload.name or f"dataset-{payload.project_id}")), None)
        if dataset is None: dataset = container.datasets.create(payload.project_id, payload.name or f"dataset-{payload.project_id}", payload.description, payload.language)
        examples = [TrainingExample(text=item.text, intent=item.intent, entities=tuple(item.entities), metadata=item.metadata, language=item.language, source=item.source, difficulty=item.difficulty, review_status=ReviewStatus(item.review_status)) for item in payload.examples]
        version = container.datasets.create_version(dataset.dataset_id, payload.version, examples, created_by=None)
        prepared, report = container.dataset_pipeline.prepare(version, {item.intent for item in examples}, {entity.get("name", entity.get("entity_type", "")) for item in examples for entity in item.entities})
        published = container.datasets.publish(prepared)
        await container.audit.record(AuditEvent("DATASET_VERSION_CREATED", project_id=payload.project_id, changes={"dataset_id": dataset.dataset_id, "version": payload.version, "checksum": published.checksum}))
        return {"success": True, "data": {"id": dataset.dataset_id, "version_id": f"{dataset.dataset_id}:{published.version}", "project_id": payload.project_id, "version": published.version, "status": published.status, "checksum": published.checksum, "statistics": report.statistics, "lineage": {"dataset_id": dataset.dataset_id, "dataset_version": published.version}}, "error": None, "request_id": request.state.request_id}
    from framework.infrastructure.sql import DatasetCatalogORM, DatasetORM
    from framework.datasets.system import DatasetVersion, ReviewStatus, TrainingExample
    catalog_id = uuid4().hex; version_id = uuid4().hex
    catalog = DatasetCatalogORM(id=catalog_id, project_id=payload.project_id, name=payload.name or f"dataset-{catalog_id}", description=payload.description, language=payload.language, schema_version=payload.schema_version, metadata_json={})
    examples = [TrainingExample(text=example.text, intent=example.intent, entities=tuple(example.entities), metadata=example.metadata, language=example.language, source=example.source, difficulty=example.difficulty, review_status=ReviewStatus(example.review_status), reviewed_by=example.reviewed_by, reviewed_at=datetime.fromisoformat(example.reviewed_at) if example.reviewed_at else None, review_notes=example.review_notes) for example in payload.examples]
    prepared, report = container.dataset_pipeline.prepare(DatasetVersion(catalog_id, payload.version, payload.project_id, tuple(examples), payload.schema_version), {example.intent for example in examples}, {entity.get("name", entity.get("entity_type", "")) for example in examples for entity in example.entities})
    row = DatasetORM(id=version_id, project_id=prepared.project_id, version=prepared.version, status=prepared.status, schema_version=prepared.schema_version, examples=[serialize_training_example(example) for example in prepared.examples], name=catalog.name, description=catalog.description, language=payload.language, statistics=report.statistics, checksum=prepared.checksum, lineage={"dataset_id": catalog_id, "dataset_version": prepared.version, "version_id": version_id, "checksum": prepared.checksum})
    await container.dataset_repository.save(row)
    catalog.current_version = row.version; catalog.status = "ready" if not report.errors else "failed"; catalog.updated_at = datetime.now(timezone.utc)
    await container.dataset_catalog_repository.save(catalog)
    await container.audit.record(AuditEvent("DATASET_VERSION_CREATED", project_id=row.project_id, changes={"dataset_id": catalog_id, "version_id": row.id, "version": row.version, "checksum": row.checksum}))
    artifact_uri = None
    if container.dataset_artifacts: artifact_uri = await container.dataset_artifacts.publish(row)
    return {"success": True, "data": {"id": catalog.id, "version_id": row.id, "project_id": row.project_id, "version": row.version, "status": row.status, "artifact_uri": artifact_uri, "checksum": row.checksum, "statistics": row.statistics, "lineage": row.lineage}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/datasets/{dataset_id}/versions")
async def create_dataset_version(dataset_id: str, payload: DatasetVersionCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.dataset_repository or not container.dataset_catalog_repository:
        catalog = container.datasets.get_dataset(dataset_id)
        if catalog is None: raise NotFoundError("Dataset not found")
        await authorize(request, x_api_key, "datasets.write", catalog.project_id)
        from framework.datasets.system import ReviewStatus, TrainingExample
        examples = [TrainingExample(text=item.text, intent=item.intent, entities=tuple(item.entities), metadata=item.metadata, language=item.language, source=item.source, difficulty=item.difficulty, review_status=ReviewStatus(item.review_status), created_by=payload.created_by) for item in payload.examples]
        version = container.datasets.create_version(dataset_id, payload.version, examples, created_by=payload.created_by)
        prepared, report = container.dataset_pipeline.prepare(version, {item.intent for item in examples}, {entity.get("name", entity.get("entity_type", "")) for item in examples for entity in item.entities})
        published = container.datasets.publish(prepared)
        return {"success": True, "data": {"id": f"{dataset_id}:{published.version}", "project_id": catalog.project_id, "version": published.version, "status": published.status, "checksum": published.checksum, "statistics": report.statistics, "lineage": {"dataset_id": dataset_id, "parent_version": catalog.current_version}}, "error": None, "request_id": request.state.request_id}
    catalog = await container.dataset_catalog_repository.get(dataset_id)
    legacy_base = await container.dataset_repository.get(dataset_id) if catalog is None else None
    if catalog is None and legacy_base is None: raise NotFoundError("Dataset not found")
    project_id = catalog.project_id if catalog else legacy_base.project_id; name = catalog.name if catalog else legacy_base.name; description = catalog.description if catalog else legacy_base.description; parent_version = catalog.current_version if catalog else legacy_base.version
    await authorize(request, x_api_key, "datasets.write", project_id)
    from framework.infrastructure.sql import DatasetORM
    from framework.datasets.system import DatasetVersion, ReviewStatus, TrainingExample
    root_id = catalog.id if catalog else (legacy_base.lineage.get("dataset_id") or legacy_base.id); version_id = uuid4().hex
    examples = [TrainingExample(text=item.text, intent=item.intent, entities=tuple(item.entities), metadata=item.metadata, language=item.language or payload.language, source=item.source, difficulty=item.difficulty, review_status=ReviewStatus(item.review_status), reviewed_by=item.reviewed_by, reviewed_at=datetime.fromisoformat(item.reviewed_at) if item.reviewed_at else None, review_notes=item.review_notes, created_by=payload.created_by) for item in payload.examples]
    prepared, report = container.dataset_pipeline.prepare(DatasetVersion(root_id, payload.version, project_id, tuple(examples), payload.schema_version), {item.intent for item in examples}, {entity.get("entity_type", entity.get("entity", "")) for item in examples for entity in item.entities})
    row = DatasetORM(id=version_id, project_id=project_id, version=prepared.version, status=prepared.status, schema_version=prepared.schema_version, examples=[serialize_training_example(item) for item in prepared.examples], name=name, description=description or "", language=payload.language, statistics=report.statistics, checksum=prepared.checksum, created_by=payload.created_by, lineage={"dataset_id": root_id, "version_id": version_id, "parent_version": parent_version, "dataset_version": prepared.version, "checksum": prepared.checksum})
    await container.dataset_repository.save(row)
    if catalog: await container.dataset_catalog_repository.update(catalog.id, current_version=row.version, status="ready" if not report.errors else "failed", updated_at=datetime.now(timezone.utc))
    await container.audit.record(AuditEvent("DATASET_VERSION_CREATED", project_id=row.project_id, changes={"dataset_id": root_id, "version_id": row.id, "version": row.version, "checksum": row.checksum, "parent": parent_version}))
    return {"success": True, "data": {"id": row.id, "project_id": row.project_id, "version": row.version, "status": row.status, "checksum": row.checksum, "statistics": row.statistics, "lineage": row.lineage}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/datasets/{dataset_id}/import")
async def import_dataset(dataset_id: str, request: Request, payload: bytes = Body(...), format: str = "json", version: str = "imported", language: str = "ar", x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.dataset_repository or not container.dataset_catalog_repository: raise FrameworkError("DATABASE_URL is required for dataset persistence")
    catalog = await container.dataset_catalog_repository.get(dataset_id)
    legacy_base = await container.dataset_repository.get(dataset_id) if catalog is None else None
    if catalog is None and legacy_base is None: raise NotFoundError("Dataset not found")
    project_id = catalog.project_id if catalog else legacy_base.project_id; name = catalog.name if catalog else legacy_base.name; description = catalog.description if catalog else legacy_base.description; root_id = catalog.id if catalog else (legacy_base.lineage.get("dataset_id") or legacy_base.id)
    await authorize(request, x_api_key, "datasets.write", project_id)
    from framework.datasets.io import CSVImporter, JSONImporter, JSONLImporter
    importer = {"json": JSONImporter, "jsonl": JSONLImporter, "csv": CSVImporter}.get(format.lower())
    if importer is None: raise FrameworkError("Unsupported dataset import format")
    imported = importer().import_data(payload, project_id=project_id, dataset_id=root_id, version=version, language=language)
    prepared, report = container.dataset_pipeline.prepare(imported, set(), set())
    from framework.infrastructure.sql import DatasetORM
    row = DatasetORM(id=uuid4().hex, project_id=project_id, version=prepared.version, status=prepared.status, schema_version=prepared.schema_version, examples=[serialize_training_example(example) for example in prepared.examples], name=name, description=description or "", language=language, statistics=report.statistics, checksum=prepared.checksum, lineage={"dataset_id": root_id, "version_id": "", "source": "import", "format": format.lower(), "checksum": prepared.checksum})
    row.lineage["version_id"] = row.id
    await container.dataset_repository.save(row)
    if catalog: await container.dataset_catalog_repository.update(catalog.id, current_version=row.version, status="ready" if not report.errors else "failed", updated_at=datetime.now(timezone.utc))
    await container.audit.record(AuditEvent("DATASET_IMPORTED", project_id=project_id, changes={"dataset_id": root_id, "version_id": row.id, "version": version, "format": format.lower(), "checksum": prepared.checksum}))
    return {"success": True, "data": {"id": root_id, "version_id": row.id, "project_id": row.project_id, "version": row.version, "status": row.status, "statistics": row.statistics, "checksum": row.checksum, "lineage": row.lineage}, "error": None, "request_id": request.state.request_id}
@app.get("/api/v1/datasets/{dataset_id}/versions")

async def list_dataset_versions(dataset_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.dataset_repository or not container.dataset_catalog_repository:
        catalog = container.datasets.get_dataset(dataset_id)
        if catalog is None: raise NotFoundError("Dataset not found")
        await authorize(request, x_api_key, "datasets.read", catalog.project_id)
        rows = container.datasets.list_versions(dataset_id)
        return {"success": True, "data": [{"id": f"{dataset_id}:{row.version}", "version": row.version, "status": row.status, "checksum": row.checksum, "statistics": row.statistics, "lineage": {"dataset_id": dataset_id}, "created_at": row.created_at.isoformat()} for row in rows], "error": None, "request_id": request.state.request_id}
    catalog = await container.dataset_catalog_repository.get(dataset_id)
    legacy_base = await container.dataset_repository.get(dataset_id) if catalog is None else None
    if catalog is None and legacy_base is None: raise NotFoundError("Dataset not found")
    project_id = catalog.project_id if catalog else legacy_base.project_id; root_id = catalog.id if catalog else (legacy_base.lineage.get("dataset_id") or legacy_base.id)
    await authorize(request, x_api_key, "datasets.read", project_id)
    rows = [row for row in await container.dataset_repository.list_project(project_id) if row.id == dataset_id or row.lineage.get("dataset_id") == root_id]
    return {"success": True, "data": [{"id": row.id, "version": row.version, "status": row.status, "checksum": row.checksum, "statistics": row.statistics, "lineage": row.lineage, "created_at": row.created_at.isoformat()} for row in rows], "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/datasets/{dataset_id}/validate")
async def validate_dataset(dataset_id: str, payload: DatasetValidateRequest, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.dataset_repository or not container.dataset_catalog_repository: raise FrameworkError("DATABASE_URL is required for dataset persistence")
    catalog = await container.dataset_catalog_repository.get(dataset_id)
    row = await container.dataset_repository.get(dataset_id) if catalog is None else None
    if catalog:
        row = next((item for item in await container.dataset_repository.list_project(catalog.project_id) if item.lineage.get("dataset_id") == catalog.id and item.version == catalog.current_version), None)
    if row is None: raise NotFoundError("Dataset not found")
    await authorize(request, x_api_key, "datasets.write", row.project_id)
    from framework.datasets.system import TrainingExample
    examples = [TrainingExample(text=item.get("text", ""), intent=item.get("intent", ""), entities=tuple(item.get("entities", [])), language=item.get("language", row.language or "ar"), metadata=item.get("metadata", {})) for item in row.examples]
    report = container.dataset_pipeline.quality(examples, payload.known_intents, payload.known_entities)
    row.status = "ready" if not report.errors else "failed"; row.statistics = report.statistics; await container.dataset_repository.save(row)
    if catalog: await container.dataset_catalog_repository.update(catalog.id, current_version=row.version, status=row.status, updated_at=datetime.now(timezone.utc))
    await container.audit.record(AuditEvent("DATASET_VALIDATED", project_id=row.project_id, changes={"dataset_id": catalog.id if catalog else row.id, "version_id": row.id, "status": row.status, "quality_score": report.quality_score}))
    return {"success": True, "data": {"id": catalog.id if catalog else row.id, "version_id": row.id, "status": row.status, "report": report.to_dict()}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/datasets/{dataset_id}/statistics")
async def dataset_statistics(dataset_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.dataset_repository or not container.dataset_catalog_repository: raise FrameworkError("DATABASE_URL is required for dataset persistence")
    catalog = await container.dataset_catalog_repository.get(dataset_id)
    row = await container.dataset_repository.get(dataset_id) if catalog is None else next((item for item in await container.dataset_repository.list_project(catalog.project_id) if item.lineage.get("dataset_id") == catalog.id and item.version == catalog.current_version), None)
    if row is None: raise NotFoundError("Dataset not found")
    await authorize(request, x_api_key, "datasets.read", row.project_id)
    return {"success": True, "data": {"dataset_id": catalog.id if catalog else row.lineage.get("dataset_id", row.id), "version_id": row.id, "version": row.version, **(row.statistics or {})}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/datasets")
async def list_datasets(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "datasets.read", project_id)
    if not container.dataset_repository or not container.dataset_catalog_repository: raise FrameworkError("DATABASE_URL is required for dataset persistence")
    catalogs = await container.dataset_catalog_repository.list_project(project_id)
    data = [{"id": item.id, "project_id": item.project_id, "name": item.name, "description": item.description, "language": item.language, "status": item.status, "schema_version": item.schema_version, "current_version": item.current_version, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()} for item in catalogs]
    if not data:
        rows = await container.dataset_repository.list_project(project_id)
        data = [{"id": row.lineage.get("dataset_id", row.id), "version_id": row.id, "project_id": row.project_id, "version": row.version, "status": row.status, "schema_version": row.schema_version, "artifact_uri": row.artifact_uri, "lineage": row.lineage, "created_at": row.created_at.isoformat()} for row in rows]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.dataset_repository or not container.dataset_catalog_repository: raise FrameworkError("DATABASE_URL is required for dataset persistence")
    catalog = await container.dataset_catalog_repository.get(dataset_id)
    row = await container.dataset_repository.get(dataset_id) if catalog is None else None
    if catalog:
        rows = [item for item in await container.dataset_repository.list_project(catalog.project_id) if item.lineage.get("dataset_id") == catalog.id]
        row = next((item for item in rows if item.version == catalog.current_version), rows[-1] if rows else None)
    if catalog is None and row is None: raise NotFoundError("Dataset not found")
    project_id = catalog.project_id if catalog else row.project_id
    await authorize(request, x_api_key, "datasets.read", project_id)
    if catalog:
        return {"success": True, "data": {"id": catalog.id, "project_id": catalog.project_id, "name": catalog.name, "description": catalog.description, "language": catalog.language, "status": catalog.status, "schema_version": catalog.schema_version, "current_version": catalog.current_version, "current_version_id": row.id if row else None, "examples": row.examples if row else [], "statistics": row.statistics if row else {}, "created_at": catalog.created_at.isoformat(), "updated_at": catalog.updated_at.isoformat()}, "error": None, "request_id": request.state.request_id}
    return {"success": True, "data": {"id": row.lineage.get("dataset_id", row.id), "version_id": row.id, "project_id": row.project_id, "version": row.version, "status": row.status, "schema_version": row.schema_version, "examples": row.examples, "artifact_uri": row.artifact_uri, "lineage": row.lineage, "created_at": row.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/training/jobs")
@app.post("/api/v1/training")
async def create_training_job(payload: TrainingCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authorize_any(request, x_api_key, ("datasets.train", "training.write"), payload.project_id)
    await container.quotas.enforce(payload.project_id, "training_jobs")
    if not container.training_job_repository or not container.redis:
        if idempotency_key:
            existing = next((item for item in container.training_jobs_memory.values() if item.get("idempotency_key") == idempotency_key and item["project_id"] == payload.project_id), None)
            if existing: return {"success": True, "data": {**existing, "idempotent_replay": True}, "error": None, "request_id": request.state.request_id}
        job_id = uuid4().hex
        job = {"id": job_id, "project_id": payload.project_id, "dataset_version": payload.dataset_version, "provider": payload.provider, "status": "queued", "metrics": {}, "artifact_uri": None, "error": None, "cancel_requested": False, "configuration": payload.training_config, "idempotency_key": idempotency_key, "created_at": datetime.now(timezone.utc).isoformat()}
        container.training_jobs_memory[job_id] = job
        from framework.training import TrainingQueueItem
        await container.training_queue.enqueue(TrainingQueueItem(job_id, payload.project_id, {"dataset_version": payload.dataset_version, "provider": payload.provider, "training_config": payload.training_config, "config_path": payload.config_path, "output_dir": payload.output_dir, "evaluation_samples": payload.evaluation_samples, "quality_gate": payload.quality_gate}))
        await container.audit.record(AuditEvent("TRAINING_STARTED", project_id=payload.project_id, changes={"job_id": job_id, "dataset_version": payload.dataset_version, "provider": payload.provider}))
        return {"success": True, "data": job, "error": None, "request_id": request.state.request_id}
    from framework.infrastructure.sql import TrainingJobORM
    if idempotency_key:
        existing = await container.training_job_repository.find_idempotency(idempotency_key)
        if existing and existing.project_id == payload.project_id: return {"success": True, "data": {"id": existing.id, "status": existing.status, "provider": existing.provider, "configuration": existing.configuration, "idempotent_replay": True}, "error": None, "request_id": request.state.request_id}
    job = TrainingJobORM(id=uuid4().hex, project_id=payload.project_id, dataset_version=payload.dataset_version, provider=payload.provider, status="queued", metrics={}, configuration=payload.training_config, request_id=request.state.request_id, idempotency_key=idempotency_key, current_stage="queued", progress=0.0, max_retries=settings.worker_max_retries)
    await container.training_job_repository.save(job)
    await container.audit.record(AuditEvent("TRAINING_STARTED", project_id=job.project_id, changes={"job_id": job.id, "dataset_version": job.dataset_version, "provider": job.provider}))
    await container.usage.record(__import__("framework.observability.usage", fromlist=["UsageEvent"]).UsageEvent(project_id=job.project_id, metric="training_job", request_id=request.state.request_id, metadata={"job_id": job.id, "provider": job.provider}))
    from framework.infrastructure.queue import RedisQueue
    await RedisQueue(container.redis.client).publish("training", {"job_id": job.id, "project_id": job.project_id, "dataset_version": job.dataset_version, "provider": job.provider, "config_path": payload.config_path, "output_dir": payload.output_dir, "training_config": payload.training_config, "evaluation_samples": payload.evaluation_samples, "quality_gate": payload.quality_gate})
    return {"success": True, "data": {"id": job.id, "status": job.status, "provider": job.provider, "configuration": job.configuration}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/training/jobs")
@app.get("/api/v1/projects/{project_id}/training")
async def list_training_jobs(project_id: str | None = None, request: Request = None, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    record = await authorize(request, x_api_key, "training.read", project_id) if project_id else await authorize(request, x_api_key, "training.read")
    if project_id is None: project_id = record.project_id if record and record.project_id != "*" else None
    if not container.training_job_repository:
        rows = [item for item in container.training_jobs_memory.values() if project_id is None or item["project_id"] == project_id]
        return {"success": True, "data": rows, "error": None, "request_id": request.state.request_id}
    rows = await container.training_job_repository.list_project(project_id) if project_id else []
    data = [{"id": row.id, "project_id": row.project_id, "dataset_version": row.dataset_version, "provider": row.provider, "status": row.status, "metrics": row.metrics, "artifact_uri": row.artifact_uri, "error": row.error, "cancel_requested": row.cancel_requested, "created_at": row.created_at.isoformat()} for row in rows]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/training/jobs/{job_id}/cancel")
@app.post("/api/v1/training/{job_id}/cancel")
async def cancel_training_job(job_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.training_job_repository:
        job = container.training_jobs_memory.get(job_id)
        if job is None: raise NotFoundError("Training job not found")
        await authorize_any(request, x_api_key, ("training.cancel", "training.write"), job["project_id"])
        job["cancel_requested"] = True; job["status"] = "cancel_requested"
        return {"success": True, "data": {"id": job_id, "status": job["status"], "cancel_requested": True}, "error": None, "request_id": request.state.request_id}
    job = await container.training_job_repository.get(job_id)
    if job is None: raise NotFoundError("Training job not found")
    await authorize_any(request, x_api_key, ("training.cancel", "training.write"), job.project_id)
    job = await container.training_job_repository.request_cancel(job_id)
    return {"success": True, "data": {"id": job.id, "status": job.status, "cancel_requested": job.cancel_requested}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/training/jobs/{job_id}")
@app.get("/api/v1/training/{job_id}")
async def get_training_job(job_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.training_job_repository:
        row = container.training_jobs_memory.get(job_id)
        if row is None: raise NotFoundError("Training job not found")
        await authorize(request, x_api_key, "training.read", row["project_id"])
        return {"success": True, "data": row, "error": None, "request_id": request.state.request_id}
    row = await container.training_job_repository.get(job_id)
    if row is None: raise NotFoundError("Training job not found")
    await authorize(request, x_api_key, "training.read", row.project_id)
    return {"success": True, "data": {"id": row.id, "project_id": row.project_id, "dataset_version": row.dataset_version, "provider": row.provider, "status": row.status, "metrics": row.metrics, "artifact_uri": row.artifact_uri, "error": row.error, "cancel_requested": row.cancel_requested, "created_at": row.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/models")
async def create_model_version(project_id: str, payload: ModelVersionCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.write", project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model persistence")
    from framework.infrastructure.sql import ModelORM
    model_id = payload.model_id or uuid4().hex
    if await container.model_repository.get(model_id): raise FrameworkError("Model already exists")
    row = ModelORM(id=model_id, project_id=project_id, version=payload.version, dataset_id=payload.dataset_id, artifact_uri=payload.artifact_uri, status="created", metrics=payload.metrics, dataset_version=payload.dataset_version, training_job_id=payload.training_job_id, provider=payload.provider, artifact_checksum=payload.artifact_checksum, evaluation_report={"metadata": payload.metadata}, deployment_history=[])
    await container.model_repository.save(row)
    await container.audit.record(AuditEvent("MODEL_CREATED", project_id=row.project_id, changes={"model_id": row.id, "version": row.version, "dataset_version": row.dataset_version, "training_job_id": row.training_job_id}))
    return {"success": True, "data": {"id": row.id, "project_id": row.project_id, "version": row.version, "dataset_id": row.dataset_id, "dataset_version": row.dataset_version, "provider": row.provider, "artifact_uri": row.artifact_uri, "artifact_checksum": row.artifact_checksum, "status": row.status, "metrics": row.metrics, "created_at": row.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/models")
@app.get("/api/v1/projects/{project_id}/models")
async def list_models(project_id: str | None = None, request: Request = None, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    record = await authorize(request, x_api_key, "models.read", project_id) if project_id else await authorize(request, x_api_key, "models.read")
    if project_id is None: project_id = record.project_id if record and record.project_id != "*" else None
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model persistence")
    rows = await container.model_repository.list_project(project_id) if project_id else []
    data = [{"id": row.id, "project_id": row.project_id, "version": row.version, "dataset_id": row.dataset_id, "artifact_uri": row.artifact_uri, "status": row.status, "metrics": row.metrics, "created_at": row.created_at.isoformat()} for row in rows]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/models/{model_id}")
async def get_model(model_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model persistence")
    row = await container.model_repository.get(model_id)
    if row is None: raise NotFoundError("Model not found")
    await authorize(request, x_api_key, "models.read", row.project_id)
    return {"success": True, "data": {"id": row.id, "project_id": row.project_id, "version": row.version, "dataset_id": row.dataset_id, "artifact_uri": row.artifact_uri, "status": row.status, "metrics": row.metrics, "created_at": row.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{model_id}/evaluate")
async def evaluate_model(model_id: str, payload: ModelEvaluationCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.evaluate", payload.project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model evaluation")
    model = await container.model_repository.get(model_id)
    if model is None: raise NotFoundError("Model not found")
    if model.project_id != payload.project_id: raise FrameworkError("Model does not belong to project")
    from framework.core.models import Entity, IntentPrediction
    samples = []
    for sample in payload.samples:
        prediction = IntentPrediction(sample.predicted_intent, sample.confidence)
        entities = [Entity(item["name"], item.get("value"), item.get("confidence", 1.0)) for item in sample.entities]
        samples.append({"prediction": prediction, "expected_intent": sample.expected_intent, "expected_entities": sample.expected_entities, "entities": entities, "action_success": sample.action_success})
    result = container.evaluation.evaluate(model.id, model.version, samples, optimize_thresholds=True)
    metrics = result.to_dict()
    await container.model_repository.update_fields(model.id, metrics={**dict(model.metrics or {}), "evaluation": metrics}, evaluation_report=metrics)
    await container.audit.record(AuditEvent("MODEL_EVALUATED", project_id=model.project_id, changes={"model_id": model.id, "version": model.version, "intent_f1": result.intent_f1, "entity_f1": result.entity_f1, "optimized_thresholds": result.optimized_thresholds}))
    return {"success": True, "data": metrics | {"model_id": result.model_id, "model_version": result.model_version}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{model_id}/optimize-thresholds")
async def optimize_model_thresholds(model_id: str, payload: ThresholdOptimizationRequest, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.evaluate", payload.project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model optimization")
    model = await container.model_repository.get(model_id)
    if model is None: raise NotFoundError("Model not found")
    if model.project_id != payload.project_id: raise FrameworkError("Model does not belong to project")
    from framework.core.models import Entity, IntentPrediction
    samples = [{"prediction": IntentPrediction(item.predicted_intent, item.confidence), "expected_intent": item.expected_intent, "expected_entities": item.expected_entities, "entities": [Entity(entity["name"], entity.get("value"), entity.get("confidence", 1.0)) for entity in item.entities], "action_success": item.action_success} for item in payload.samples]
    from framework.models.thresholds import ThresholdOptimizer
    optimizer = ThresholdOptimizer(step=payload.step, minimum_accept=payload.minimum_accept, minimum_clarification=payload.minimum_clarification)
    result = container.evaluation.evaluate(model.id, model.version, samples, optimize_thresholds=False)
    optimized = optimizer.optimize(samples).to_dict(); report = {**result.to_dict(), "optimized_thresholds": optimized}
    await container.model_repository.update_fields(model.id, metrics={**dict(model.metrics or {}), "evaluation": report}, evaluation_report=report)
    await container.audit.record(AuditEvent("MODEL_THRESHOLDS_OPTIMIZED", project_id=model.project_id, changes={"model_id": model.id, "version": model.version, "thresholds": optimized}))
    return {"success": True, "data": report, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/models/compare")
async def compare_models(project_id: str, payload: ModelComparisonRequest, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.read", project_id)
    if payload.project_id != project_id: raise FrameworkError("Comparison project mismatch")
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model comparison")
    from framework.models.evaluation import EvaluationResult
    results = []
    for model_id in payload.model_ids:
        model = await container.model_repository.get(model_id)
        if model is None: raise NotFoundError(f"Model not found: {model_id}")
        if model.project_id != project_id: raise FrameworkError("Model does not belong to project")
        report = dict(model.evaluation_report or {})
        if "evaluation" in report: report = dict(report["evaluation"])
        try: results.append(EvaluationResult(**{key: report[key] for key in EvaluationResult.__dataclass_fields__ if key in report}))
        except (TypeError, KeyError) as exc: raise FrameworkError(f"Model {model_id} has no complete evaluation report") from exc
    from framework.models.comparison import ModelComparator
    comparator = ModelComparator(intent_f1_weight=payload.intent_f1_weight, entity_f1_weight=payload.entity_f1_weight, fallback_weight=payload.fallback_weight)
    result = comparator.compare(results, require_regression_pass=payload.require_regression_pass)
    await container.audit.record(AuditEvent("MODELS_COMPARED", project_id=project_id, changes={"model_ids": payload.model_ids, "winner_model_id": result.winner_model_id, "winner_model_version": result.winner_model_version}))
    return {"success": True, "data": result.to_dict(), "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{model_id}/runtime/load")
async def load_model_runtime(model_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model runtime")
    model = await container.model_repository.get(model_id)
    if model is None: raise NotFoundError("Model not found")
    await authorize_any(request, x_api_key, ("models.runtime", "models.deploy"), model.project_id)
    handle = await container.runtime.load(model)
    await container.audit.record(AuditEvent("MODEL_RUNTIME_READY", project_id=model.project_id, changes={"model_id": model.id, "version": model.version}))
    return {"success": True, "data": handle.to_dict(), "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/models/{model_id}/runtime")
async def model_runtime_status(model_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model runtime")
    model = await container.model_repository.get(model_id)
    if model is None: raise NotFoundError("Model not found")
    await authorize_any(request, x_api_key, ("models.runtime", "models.read"), model.project_id)
    return {"success": True, "data": await container.runtime.status(model_id), "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{model_id}/runtime/serve")
async def serve_model_runtime(model_id: str, payload: ModelRuntimeServeRequest, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.runtime", payload.project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model runtime")
    model = await container.model_repository.get(model_id)
    if model is None: raise NotFoundError("Model not found")
    if model.project_id != payload.project_id: raise FrameworkError("Model does not belong to project")
    result = await container.runtime.serve(model, payload.text, payload.metadata)
    return {"success": True, "data": result, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{model_id}/runtime/unload")
async def unload_model_runtime(model_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model runtime")
    model = await container.model_repository.get(model_id)
    if model is None: raise NotFoundError("Model not found")
    await authorize_any(request, x_api_key, ("models.runtime", "models.deploy"), model.project_id)
    result = await container.runtime.unload(model_id)
    await container.audit.record(AuditEvent("MODEL_RUNTIME_UNLOADED", project_id=model.project_id, changes={"model_id": model.id, "version": model.version}))
    return {"success": True, "data": result, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{model_id}/health")
async def update_model_health(model_id: str, payload: ModelHealthUpdate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.deploy", payload.project_id)
    if not container.deployment or not container.model_repository: raise FrameworkError("DATABASE_URL is required for model promotion")
    model = await container.model_repository.get(model_id)
    if model is None: raise NotFoundError("Model not found")
    if model.project_id != payload.project_id: raise FrameworkError("Model does not belong to project")
    result = await container.deployment.promote_canary(payload.project_id, model_id, payload.healthy, payload.reason)
    return {"success": True, "data": result.__dict__, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/deployments")
async def deploy_model_version(payload: ModelDeploymentRequest, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.deploy", payload.project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model deployment")
    model = await container.model_repository.get(payload.model_id)
    if model is None: raise NotFoundError("Model not found")
    if model.project_id != payload.project_id: raise FrameworkError("Model does not belong to project")
    if model.status not in {"ready", "deployed"}: raise FrameworkError("Model quality gate must pass before deployment")
    evaluation_report = dict(model.evaluation_report or {})
    quality = dict(evaluation_report.get("quality_gate", {})); regression = evaluation_report.get("evaluation", {}).get("regression_passed", True)
    decision = container.promotion_policy.decide(quality_passed=quality.get("passed", True), regression_passed=regression is not False, human_approved=payload.human_approved, auto_deploy=payload.auto_deploy, failures=quality.get("failures", []))
    if payload.environment == "production" and not decision.passed: raise FrameworkError(f"Model promotion rejected: {', '.join(decision.failures)}")
    rows = await container.model_repository.list_project(payload.project_id)
    previous = next((item for item in rows if item.deployment_environment == payload.environment and item.status == "deployed" and item.id != model.id), None)
    if previous:
        await container.model_repository.update_fields(previous.id, status="ready", deployment_environment=payload.environment)
    history = list(model.deployment_history or [])
    history.append({"environment": payload.environment, "model_id": model.id, "version": model.version, "action": "canary" if payload.canary else "deploy", "created_at": datetime.now(timezone.utc).isoformat()})
    updated = await container.model_repository.update_fields(model.id, status="canary" if payload.canary else "deployed", deployment_environment=payload.environment, deployment_history=history)
    await container.audit.record(AuditEvent("MODEL_DEPLOYED", project_id=updated.project_id, changes={"model_id": updated.id, "version": updated.version, "environment": payload.environment, "previous_model_id": previous.id if previous else None}))
    return {"success": True, "data": {"model_id": updated.id, "version": updated.version, "environment": payload.environment, "status": updated.status, "previous_model_id": previous.id if previous else None, "history": updated.deployment_history}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/deploy")
async def deploy_model(payload: DeploymentCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.deploy", payload.project_id)
    if not container.deployment or not container.model_repository:
        raise FrameworkError("DATABASE_URL is required for model deployment")
    model = await container.model_repository.get(payload.model_id)
    if model is None: raise NotFoundError("Model not found")
    if model.project_id != payload.project_id: raise FrameworkError("Model does not belong to project")
    if model.status not in {"ready", "deployed"}: raise FrameworkError("Model quality gate must pass before deployment")
    result = await container.deployment.deploy(payload.project_id, payload.model_id, payload.canary)
    return {"success": True, "data": result.__dict__, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/models/rollback-history")
async def model_rollback_history(project_id: str, request: Request, environment: str = "production", x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.read", project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model persistence")
    rows = await container.model_repository.list_project(project_id)
    history = [event for row in rows for event in (row.deployment_history or []) if event.get("environment") == environment]
    return {"success": True, "data": sorted(history, key=lambda event: event.get("created_at", "")), "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/models/rollback")
async def rollback_model_version(project_id: str, request: Request, environment: str = "production", x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.rollback", project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model deployment")
    rows = await container.model_repository.list_project(project_id)
    deployed = next((row for row in rows if row.deployment_environment == environment and row.status == "deployed"), None)
    history = sorted([event for row in rows for event in (row.deployment_history or []) if event.get("environment") == environment and event.get("action") == "deploy"], key=lambda event: event.get("created_at", ""))
    if deployed is None or len(history) < 2: raise FrameworkError("No previous model available for rollback")
    previous_id = history[-2]["model_id"]
    previous = await container.model_repository.get(previous_id)
    if previous is None: raise NotFoundError("Previous model not found")
    await container.model_repository.update_fields(deployed.id, status="rolled_back")
    updated_history = list(previous.deployment_history or []); updated_history.append({"environment": environment, "model_id": previous.id, "version": previous.version, "action": "rollback", "created_at": datetime.now(timezone.utc).isoformat()})
    updated = await container.model_repository.update_fields(previous.id, status="deployed", deployment_environment=environment, deployment_history=updated_history)
    await container.audit.record(AuditEvent("MODEL_ROLLED_BACK", project_id=updated.project_id, changes={"model_id": updated.id, "version": updated.version, "environment": environment, "rolled_back_model_id": deployed.id}))
    return {"success": True, "data": {"model_id": updated.id, "version": updated.version, "environment": environment, "status": updated.status, "rolled_back_model_id": deployed.id, "history": updated.deployment_history}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/models/{project_id}/rollback")
async def rollback_model(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize_any(request, x_api_key, ("models.rollback", "models.deploy"), project_id)
    if not container.deployment:
        raise FrameworkError("DATABASE_URL is required for model deployment")
    result = await container.deployment.rollback(project_id)
    return {"success": True, "data": result.__dict__, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/model-selection")
async def select_project_model(project_id: str, payload: dict, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.deploy", project_id)
    environment = payload.get("environment", "production")
    if environment not in {"development", "staging", "production"}: raise FrameworkError("Invalid environment")
    model_id, version = payload.get("model_id"), payload.get("version")
    if not model_id or not version: raise FrameworkError("model_id and version are required")
    if container.model_repository:
        model = await container.model_repository.get(model_id)
        if model is None or model.project_id != project_id or model.version != version or model.status not in {"ready", "deployed"}: raise AuthorizationError("Model is not available for this project/environment")
    else:
        model = container.models.get(model_id, version)
        if model is None or model.project_id != project_id or model.status not in {"ready", "deployed"}: raise AuthorizationError("Model is not available for this project/environment")
    project = await container.developers.get_project(project_id)
    configuration = dict(getattr(project, "configuration", {}) or {}); by_environment = dict(configuration.get("models", {}) or {}); by_environment[environment] = {"model_id": model_id, "version": version}; configuration["models"] = by_environment
    updated = await container.developers.update_project(project_id, configuration=configuration)
    await container.audit.record(AuditEvent("MODEL_SELECTED", project_id=project_id, changes={"model_id": model_id, "version": version, "environment": environment}))
    return {"success": True, "data": {"project_id": project_id, "environment": environment, "model_id": model_id, "version": version, "configuration": updated.configuration}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/webhooks")
async def create_webhook(project_id: str, payload: dict, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "webhooks.write", project_id)
    from framework.core.integrations import WebhookSubscription
    import secrets
    webhook_id = "wh_" + uuid4().hex
    secret = "whsec_" + secrets.token_urlsafe(32)
    events = payload.get("events") or [payload.get("event", "*")]
    subscriptions = []
    for event in events:
        metadata = {"webhook_id": webhook_id, "project_id": project_id, "status": "active"}
        subscriptions.append(container.webhooks.register(WebhookSubscription(event, payload["url"], secret, timeout_seconds=float(payload.get("timeout_seconds", 10)), max_retries=min(int(payload.get("max_retries", 3)), 3), metadata=metadata)))
        if container.webhook_repository:
            from framework.infrastructure.sql import WebhookSubscriptionORM
            await container.webhook_repository.save(WebhookSubscriptionORM(id=webhook_id + "_" + event.replace(".", "_"), project_id=project_id, event_name=event, url=payload["url"], secret_ciphertext=container.webhook_cipher.encrypt(secret), timeout_seconds=float(payload.get("timeout_seconds", 10)), max_retries=min(int(payload.get("max_retries", 3)), 3), metadata_json=metadata))
    await container.audit.record(AuditEvent("WEBHOOK_CREATED", project_id=project_id, changes={"webhook_id": webhook_id, "events": events, "url": payload["url"]}))
    return {"success": True, "data": {"webhook_id": webhook_id, "project_id": project_id, "url": payload["url"], "events": events, "status": "active", "secret": secret}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/webhooks")
async def list_webhooks(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "webhooks.read", project_id)
    grouped = {}
    persisted = await container.webhook_repository.list_project(project_id) if container.webhook_repository else []
    for row in persisted:
        if not any(s.metadata.get("webhook_id") == row.metadata_json.get("webhook_id") and s.event_name == row.event_name for s in container.webhooks.list_project(project_id)):
            from framework.core.integrations import WebhookSubscription
            container.webhooks.register(WebhookSubscription(row.event_name, row.url, container.webhook_cipher.decrypt(row.secret_ciphertext), row.timeout_seconds, row.max_retries, dict(row.metadata_json or {})))
    for sub in container.webhooks.list_project(project_id):
        wid = sub.metadata.get("webhook_id"); grouped.setdefault(wid, {"webhook_id": wid, "project_id": project_id, "url": sub.url, "events": [], "status": sub.metadata.get("status", "active")}); grouped[wid]["events"].append(sub.event_name)
    return {"success": True, "data": list(grouped.values()), "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/webhooks/deliveries")
async def list_webhook_deliveries(project_id: str, request: Request, limit: int = 100, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "webhooks.read", project_id)
    if not container.webhook_delivery_log_repository: raise FrameworkError("DATABASE_URL is required for webhook delivery logs")
    rows = await container.webhook_delivery_log_repository.list_project(project_id, limit)
    data = [{"id": row.id, "project_id": row.project_id, "webhook_id": row.webhook_id, "event_id": row.event_id, "event_name": row.event_name, "status_code": row.status_code, "attempt": row.attempt, "duration_ms": row.duration_ms, "success": row.success, "error": row.error, "created_at": row.created_at.isoformat()} for row in rows]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.delete("/api/v1/projects/{project_id}/webhooks/{webhook_id}")
async def delete_webhook(project_id: str, webhook_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "webhooks.write", project_id)
    removed = container.webhooks.remove(webhook_id, project_id)
    if container.webhook_repository:
        for row in await container.webhook_repository.list_project(project_id):
            if row.metadata_json.get("webhook_id") == webhook_id: await container.webhook_repository.delete_row(row.id, project_id); removed = True
    if not removed: raise NotFoundError("Webhook not found")
    await container.audit.record(AuditEvent("WEBHOOK_DELETED", project_id=project_id, changes={"webhook_id": webhook_id}))
    return {"success": True, "data": {"webhook_id": webhook_id, "status": "deleted"}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/bots")
async def list_bots(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "bots.read", project_id)
    bots = container.bots.list_for_project(project_id)
    if inspect.isawaitable(bots): bots = await bots
    data = [{"id": bot.id, "project_id": bot.project_id, "name": bot.name, "status": bot.status, "webhook_url": bot.webhook_url, "metadata": bot.metadata, "created_at": bot.created_at.isoformat()} for bot in bots]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/bots/{bot_id}")
async def get_bot(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "bots.read")
    bot = container.bots.get(bot_id)
    if inspect.isawaitable(bot): bot = await bot
    if bot is None: raise NotFoundError("Bot not found")
    record = await authorize(request, x_api_key, "bots.read", bot.project_id)
    return {"success": True, "data": {"id": bot.id, "project_id": bot.project_id, "name": bot.name, "status": bot.status, "webhook_url": bot.webhook_url, "metadata": bot.metadata, "created_at": bot.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/projects/{project_id}/bots")
async def register_bot(project_id: str, payload: dict, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "bots.manage", project_id)
    await container.quotas.enforce(project_id, "bots")
    from framework.channels.management import TelegramBot
    token = payload.get("token")
    token_ref = payload.get("token_secret_ref") or f"telegram/{project_id}/{payload.get('name', 'bot')}"
    if token:
        if not token.startswith("-") and ":" not in token: raise FrameworkError("Invalid Telegram token format")
        if not hasattr(container.bot_secrets, "set"): raise FrameworkError("Configure a writable secret manager before registering tokens")
        container.bot_secrets.set(token_ref, token)
    else:
        token = container.bot_secrets.get(token_ref)
    if not token: raise FrameworkError("Telegram token or token_secret_ref is required")
    from framework.channels.telegram import TelegramAdapter
    health = await TelegramAdapter(token).health()
    if health.get("status") != "ready": raise FrameworkError("Telegram token validation failed", details={"status": health.get("status")})
    metadata = dict(payload.get("metadata", {})); metadata.update({"telegram_username": health.get("username"), "telegram_id": health.get("bot_id")})
    bot = TelegramBot(project_id, payload["name"], token_ref, webhook_secret_ref=f"telegram-webhook/{project_id}/{secrets.token_hex(8)}", metadata=metadata)
    if not hasattr(container.bot_secrets, "set"): raise FrameworkError("Configure a writable secret manager before registering tokens")
    container.bot_secrets.set(bot.webhook_secret_ref, secrets.token_urlsafe(32))
    bot = container.bots.register(bot)
    if inspect.isawaitable(bot): bot = await bot
    await container.audit.record(AuditEvent("TELEGRAM_BOT_REGISTERED", project_id=project_id, changes={"bot_id": bot.id, "telegram_id": health.get("bot_id")}))
    await container.usage.record(__import__("framework.observability.usage", fromlist=["UsageEvent"]).UsageEvent(project_id=project_id, metric="bot", request_id=request.state.request_id, metadata={"bot_id": bot.id}))
    return {"success": True, "data": {"id": bot.id, "project_id": bot.project_id, "name": bot.name, "status": bot.status, "telegram_username": metadata.get("telegram_username")}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/validate")
async def validate_bot(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = container.bots.get(bot_id); current = await current if inspect.isawaitable(current) else current
    if current is None: raise NotFoundError("Bot not found")
    await authorize(request, x_api_key, "bots.manage", current.project_id)
    token = container.bot_secrets.get(current.token_secret_ref)
    if not token: raise FrameworkError("Telegram token is unavailable")
    from framework.channels.telegram import TelegramAdapter
    health = await TelegramAdapter(token).health()
    return {"success": True, "data": health, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/connect")
async def connect_bot(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = container.bots.get(bot_id); current = await current if inspect.isawaitable(current) else current
    if current is None: raise NotFoundError("Bot not found")
    await authorize(request, x_api_key, "bots.manage", current.project_id)
    token = container.bot_secrets.get(current.token_secret_ref)
    if not token: raise FrameworkError("Telegram token is unavailable")
    from framework.channels.telegram import TelegramAdapter
    health = await TelegramAdapter(token).health()
    if health.get("status") != "ready": raise FrameworkError("Telegram connection validation failed")
    bot = container.bots.enable(bot_id); bot = await bot if inspect.isawaitable(bot) else bot
    await container.audit.record(AuditEvent("TELEGRAM_BOT_CONNECTED", project_id=current.project_id, changes={"bot_id": bot_id}))
    return {"success": True, "data": {"id": bot.id, "status": bot.status, "health": health}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/bots/{bot_id}/status")
async def bot_status(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = container.bots.get(bot_id); current = await current if inspect.isawaitable(current) else current
    if current is None: raise NotFoundError("Bot not found")
    await authorize(request, x_api_key, "bots.read", current.project_id)
    token = container.bot_secrets.get(current.token_secret_ref)
    health = {"status": "not_configured", "channel": "telegram"} if not token else await __import__("framework.channels.telegram", fromlist=["TelegramAdapter"]).TelegramAdapter(token).health()
    return {"success": True, "data": {"id": current.id, "project_id": current.project_id, "status": current.status, "webhook_url": current.webhook_url, "health": health}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/enable")
async def enable_bot(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = container.bots.get(bot_id); current = await current if inspect.isawaitable(current) else current
    if current is None: raise NotFoundError("Bot not found")
    await authorize(request, x_api_key, "bots.manage", current.project_id)
    bot = container.bots.enable(bot_id)
    if inspect.isawaitable(bot): bot = await bot
    return {"success": True, "data": {"id": bot.id, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/bots/{bot_id}/disable")
async def disable_bot(bot_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = container.bots.get(bot_id); current = await current if inspect.isawaitable(current) else current
    if current is None: raise NotFoundError("Bot not found")
    await authorize(request, x_api_key, "bots.manage", current.project_id)
    bot = container.bots.disable(bot_id)
    if inspect.isawaitable(bot): bot = await bot
    return {"success": True, "data": {"id": bot.id, "status": bot.status}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/messages/stream")
async def stream_message(payload: MessageCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    import json
    result = await process_message(payload, request, x_api_key)
    async def events():
        data = result.get("data") or {}
        for stage in data.get("trace", []): yield f"event: {stage.lower()}\\ndata: {json.dumps({'stage': stage, 'request_id': result.get('request_id')}, ensure_ascii=False)}\\n\\n"
        yield f"event: completed\\ndata: {json.dumps(result, ensure_ascii=False)}\\n\\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/v1/bots/{bot_id}/webhook")
async def set_bot_webhook(bot_id: str, payload: dict, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = container.bots.get(bot_id); current = await current if inspect.isawaitable(current) else current
    if current is None: raise NotFoundError("Bot not found")
    await authorize(request, x_api_key, "bots.manage", current.project_id)
    token = container.bot_secrets.get(current.token_secret_ref)
    if not token: raise FrameworkError("Telegram token is unavailable")
    from framework.channels.telegram import TelegramAdapter
    webhook_secret = container.bot_secrets.get(current.webhook_secret_ref) if current.webhook_secret_ref else None
    await TelegramAdapter(token).set_webhook(payload["url"], secret_token=webhook_secret)
    bot = container.bots.set_webhook(bot_id, payload["url"])
    if inspect.isawaitable(bot): bot = await bot
    return {"success": True, "data": {"id": bot.id, "webhook_url": bot.webhook_url}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/projects/{project_id}/api-keys")
async def list_api_keys(project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "keys.read", project_id)
    keys = await container.developers.list_api_keys(project_id)
    data = [{"key_id": key.key_id, "project_id": key.project_id, "name": key.name, "prefix": key.prefix, "environment": key.environment, "key_type": key.key_type, "permissions": sorted(key.permissions), "status": key.status, "expires_at": key.expires_at.isoformat() if key.expires_at else None, "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None, "metadata": key.metadata, "created_at": key.created_at.isoformat()} for key in keys]
    return {"success": True, "data": data, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = await container.developers.get_api_key(key_id)
    await authorize(request, x_api_key, "keys.write", current.project_id)
    created = await container.developers.rotate_api_key(key_id)
    await container.audit.record(AuditEvent("API_KEY_ROTATED", project_id=current.project_id, changes={"old_key_id": key_id, "new_key_id": created.key_id, "prefix": created.prefix}))
    return {"success": True, "data": {"key_id": created.key_id, "secret": created.secret, "prefix": created.prefix, "project_id": created.project_id, "environment": created.environment, "key_type": created.key_type}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = await container.developers.get_api_key(key_id)
    await authorize(request, x_api_key, "keys.write", current.project_id)
    await container.developers.revoke_api_key(key_id)
    await container.audit.record(AuditEvent("API_KEY_REVOKED", project_id=current.project_id, changes={"key_id": key_id}))
    return {"success": True, "data": {"key_id": key_id, "status": "revoked"}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys/{key_id}/disable")
async def disable_api_key(key_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = await container.developers.get_api_key(key_id)
    await authorize(request, x_api_key, "keys.write", current.project_id)
    await container.developers.disable_api_key(key_id)
    return {"success": True, "data": {"key_id": key_id, "status": "disabled"}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/api-keys/{key_id}/expire")
async def expire_api_key(key_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    current = await container.developers.get_api_key(key_id)
    await authorize(request, x_api_key, "keys.write", current.project_id)
    await container.developers.expire_api_key(key_id)
    return {"success": True, "data": {"key_id": key_id, "status": "expired"}, "error": None, "request_id": request.state.request_id}

async def _process_telegram_update(project_id: str, bot_id: str, payload: dict, request: Request):
    from framework.channels.telegram import TelegramAdapter
    from framework.channels.webhooks import TelegramWebhookVerifier
    from framework.errors import AuthenticationError
    bot = container.bots.get(bot_id); bot = await bot if inspect.isawaitable(bot) else bot
    if bot is None or bot.project_id != project_id: raise NotFoundError("Telegram bot not found")
    if bot.status != "enabled": raise FrameworkError("Telegram bot is not connected")
    token = container.bot_secrets.get(bot.token_secret_ref)
    secret = container.bot_secrets.get(bot.webhook_secret_ref) if bot.webhook_secret_ref else None
    if not token or not secret: raise FrameworkError("Telegram bot credentials are unavailable")
    if not TelegramWebhookVerifier(secret).verify(request.headers.get("X-Telegram-Bot-Api-Secret-Token")):
        raise AuthenticationError("Invalid Telegram webhook secret")
    adapter = TelegramAdapter(token)
    if container.redis:
        from framework.infrastructure.queue import RedisQueue
        event_id = await RedisQueue(container.redis.client).publish("telegram_updates", {"project_id": project_id, "bot_id": bot_id, "payload": payload, "request_id": request.state.request_id})
        return {"success": True, "data": {"accepted": True, "event_id": event_id, "bot_id": bot_id}, "error": None, "request_id": request.state.request_id}
    message = await adapter.normalize(payload, project_id=project_id)
    result = await container.messages.process(message)
    await adapter.send(result.response, recipient_id=message.chat_id)
    return {"success": True, "data": {"message_id": message.message_id, "bot_id": bot_id, "intent": result.intent.name if result.intent else None, "trace": result.trace}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/webhooks/telegram/{project_id}/{bot_id}")
async def telegram_bot_webhook(project_id: str, bot_id: str, payload: dict, request: Request):
    return await _process_telegram_update(project_id, bot_id, payload, request)

@app.post("/api/v1/webhooks/telegram/{project_id}")
async def telegram_webhook(project_id: str, payload: dict, request: Request):
    bots = container.bots.list_for_project(project_id); bots = await bots if inspect.isawaitable(bots) else bots
    bot = next((item for item in bots if item.status == "enabled"), None)
    if bot is None and settings.database_url == "memory://":
        from framework.channels.telegram import TelegramAdapter
        adapter = TelegramAdapter(settings.telegram_bot_token)
        message = await adapter.normalize(payload, project_id=project_id)
        result = await container.messages.process(message)
        await adapter.send(result.response, recipient_id=message.chat_id)
        return {"success": True, "data": {"message_id": message.message_id, "intent": result.intent.name if result.intent else None, "trace": result.trace}, "error": None, "request_id": request.state.request_id}
    if bot is None: raise NotFoundError("No enabled Telegram bot for project")
    return await _process_telegram_update(project_id, bot.id, payload, request)

@app.post("/api/v1/messages")
async def process_message(payload: MessageCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    record = await authenticate_api_request(request, container, x_api_key)
    require_permission(record, "messages.write")
    await container.quotas.enforce_request(payload.project_id)
    started_at = datetime.now(timezone.utc)
    from framework.core.models import IncomingMessage
    metadata = dict(payload.metadata); metadata.update({"permissions": sorted(record.permissions) if record else [], "idempotency_key": request.headers.get("Idempotency-Key"), "api_key_id": record.key_id if record else None, "request_id": request.state.request_id, "endpoint": request.url.path, "environment": record.environment if record else settings.app_env})
    message = IncomingMessage(project_id=payload.project_id, channel=payload.channel, user_id=payload.user_id, chat_id=payload.chat_id or payload.user_id, text=payload.text, session_id=payload.session_id, metadata=metadata)
    result = await container.messages.process(message)
    data = {"id": message.message_id, "object": "message", "success": result.success, "intent": result.intent.name if result.intent else None, "intent_detail": {"name": result.intent.name, "confidence": result.intent.confidence} if result.intent else None, "confidence": result.intent.confidence if result.intent else None, "entities": [{"name": e.name, "value": e.value, "confidence": e.confidence, "start": e.start, "end": e.end} for e in result.entities], "text": result.response.text, "response": {"text": result.response.text, "messages": result.response.rendered_messages(), "metadata": result.response.metadata}, "session_id": result.session_id or payload.session_id, "request_id": result.request_id or request.state.request_id, "trace_id": result.trace_id, "trace": result.trace, "usage": {"processing_time_ms": result.timings.get("total") if result.timings else None}}
    await container.usage.record(__import__("framework.observability.usage", fromlist=["UsageEvent"]).UsageEvent(project_id=payload.project_id, metric="api_request", request_id=request.state.request_id, metadata={"api_key_id": record.key_id if record else None, "endpoint": request.url.path, "status": 200 if result.success else 500, "latency_ms": (datetime.now(timezone.utc) - started_at).total_seconds() * 1000, "model": data.get("model_version")}))
    return {"success": result.success, "data": data, "error": result.errors[0] if result.errors else None, "request_id": request.state.request_id}


@app.get("/api/v1/models/{model_id}/versions")
async def list_model_versions_spec06(model_id: str, project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.read", project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model persistence")
    rows = [row for row in await container.model_repository.list_project(project_id) if row.id == model_id or row.evaluation_report.get("model_id") == model_id]
    return {"success": True, "data": [{"id": row.id, "model_id": model_id, "version": row.version, "artifact_uri": row.artifact_uri, "dataset_version": row.dataset_version, "training_job_id": row.training_job_id, "metrics": row.metrics, "status": row.status, "created_at": row.created_at.isoformat()} for row in rows], "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/models/{model_id}/versions/{version}")
async def get_model_version_spec06(model_id: str, version: str, project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.read", project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model persistence")
    rows = [row for row in await container.model_repository.list_project(project_id) if row.id == model_id and row.version == version]
    if not rows: raise NotFoundError("Model version not found")
    row = rows[0]
    return {"success": True, "data": {"id": row.id, "model_id": model_id, "version": row.version, "project_id": row.project_id, "artifact_uri": row.artifact_uri, "artifact_checksum": row.artifact_checksum, "dataset_version": row.dataset_version, "training_job_id": row.training_job_id, "metrics": row.metrics, "evaluation": row.evaluation_report, "status": row.status, "lineage": row.evaluation_report.get("lineage", {}), "created_at": row.created_at.isoformat()}, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/deployments")
async def create_deployment_spec06(payload: ModelDeploymentRequest, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.deploy", payload.project_id)
    if not container.model_repository: raise FrameworkError("DATABASE_URL is required for model deployment")
    model = await container.model_repository.get(payload.model_id)
    if model is None or model.project_id != payload.project_id: raise NotFoundError("Model not found")
    if model.status not in {"ready", "deployed"}: raise FrameworkError("Quality gate must pass before deployment")
    if not model.artifact_uri: raise FrameworkError("Model artifact is required")
    record = await container.deployment_manager.deploy(payload.project_id, model.id, model.version, model.artifact_uri, environment=payload.environment, alias=payload.environment)
    await container.audit.record(AuditEvent("MODEL_DEPLOYED", project_id=payload.project_id, changes={"model_id": model.id, "version": model.version, "environment": payload.environment}))
    return {"success": True, "data": record, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/deployments")
async def list_deployments_spec06(project_id: str, request: Request, environment: str | None = None, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.read", project_id)
    rows = []
    for key, history in container.deployment_manager.history.items():
        if key[0] == project_id and (environment is None or key[1] == environment): rows.extend(history)
    return {"success": True, "data": rows, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/deployments/{deployment_id}")
async def get_deployment_spec06(deployment_id: str, project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.read", project_id)
    for history in container.deployment_manager.history.values():
        for record in history:
            if record["deployment_id"] == deployment_id and record["project_id"] == project_id: return {"success": True, "data": record, "error": None, "request_id": request.state.request_id}
    raise NotFoundError("Deployment not found")

@app.post("/api/v1/deployments/{deployment_id}/rollback")
async def rollback_deployment_spec06(deployment_id: str, project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.rollback", project_id)
    target = None
    for key, history in container.deployment_manager.history.items():
        if key[0] == project_id:
            target = (key, history)
            if any(item["deployment_id"] == deployment_id for item in history): break
    if target is None: raise NotFoundError("Deployment not found")
    key, _ = target; result = await container.deployment_manager.rollback(project_id, environment=key[1], alias=key[2])
    await container.audit.record(AuditEvent("MODEL_ROLLED_BACK", project_id=project_id, changes={"deployment_id": deployment_id, "environment": key[1]}))
    return {"success": True, "data": result, "error": None, "request_id": request.state.request_id}

@app.post("/api/v1/evaluations")
async def create_evaluation_spec06(payload: ModelEvaluationCreate, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.evaluate", payload.project_id)
    samples = []
    for sample in payload.samples:
        prediction = IntentPrediction(sample.predicted_intent, sample.confidence)
        entities = [Entity(item.get("name", ""), item.get("value"), float(item.get("confidence", 1.0))) for item in sample.entities]
        samples.append({"prediction": prediction, "expected_intent": sample.expected_intent, "expected_entities": sample.expected_entities, "entities": entities, "action_success": sample.action_success})
    result = container.evaluation.evaluate("ad-hoc", "candidate", samples)
    evaluation_id = uuid4().hex
    await container.audit.record(AuditEvent("EVALUATION_COMPLETED", project_id=payload.project_id, changes={"evaluation_id": evaluation_id, "metrics": result.to_dict()}))
    return {"success": True, "data": {"id": evaluation_id, "project_id": payload.project_id, "report": result.to_dict()}, "error": None, "request_id": request.state.request_id}

@app.get("/api/v1/evaluations/{evaluation_id}")
async def get_evaluation_spec06(evaluation_id: str, project_id: str, request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    await authorize(request, x_api_key, "models.evaluate", project_id)
    events = await container.audit.list_project(project_id, 1000)
    for event in events:
        if event.event_name == "EVALUATION_COMPLETED" and event.changes.get("evaluation_id") == evaluation_id: return {"success": True, "data": {"id": evaluation_id, "project_id": project_id, "report": event.changes.get("metrics", {})}, "error": None, "request_id": request.state.request_id}
    raise NotFoundError("Evaluation not found")
