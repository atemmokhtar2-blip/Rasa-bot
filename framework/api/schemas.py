from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Any

class DeveloperCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr

class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    environment: str | None = Field(default=None, pattern="^(development|staging|production)$")
    status: str | None = Field(default=None, pattern="^(active|suspended|archived)$")
    configuration: dict[str, Any] | None = None

class ProjectCreate(BaseModel):
    owner_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

class APIKeyCreate(BaseModel):
    developer_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    name: str = Field(default="default", min_length=1, max_length=255)
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    key_type: str = Field(default="development", pattern="^(live|test|development)$")
    permissions: set[str] = set()
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class MessageCreate(BaseModel):
    project_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    chat_id: str | None = None
    channel: str = "api"
    text: str | None = Field(default=None, max_length=10000)
    session_id: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False

class TrainingExampleInput(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    intent: str = Field(min_length=1, max_length=255)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    language: str = "ar"
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = "manual"
    difficulty: str = "medium"
    review_status: str = "unreviewed"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_notes: str | None = None

class DatasetCreate(BaseModel):
    project_id: str = Field(min_length=1)
    version: str = Field(min_length=1, max_length=64)
    schema_version: str = "1"
    examples: list[TrainingExampleInput]
    name: str | None = None
    description: str = ""
    language: str = "ar"

class DatasetVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    schema_version: str = "1"
    examples: list[TrainingExampleInput] = Field(default_factory=list)
    language: str = "ar"
    created_by: str | None = None

class DatasetValidateRequest(BaseModel):
    known_intents: set[str] = set()
    known_entities: set[str] = set()

class TrainingCreate(BaseModel):
    project_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    config_path: str = "config.yml"
    output_dir: str = "./data/models"
    provider: str = "rasa"
    training_config: dict[str, Any] = Field(default_factory=dict)
    evaluation_samples: list[dict[str, Any]] = Field(default_factory=list)
    quality_gate: dict[str, float | bool] = Field(default_factory=dict)

class EvaluationSample(BaseModel):
    expected_intent: str
    predicted_intent: str
    confidence: float = Field(ge=0, le=1)
    expected_entities: dict[str, Any] = Field(default_factory=dict)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    action_success: bool = False

class ModelEvaluationCreate(BaseModel):
    project_id: str = Field(min_length=1)
    samples: list[EvaluationSample] = Field(min_length=1)

class ModelHealthUpdate(BaseModel):
    project_id: str = Field(min_length=1)
    healthy: bool
    reason: str = Field(default="", max_length=1000)

class ThresholdOptimizationRequest(BaseModel):
    project_id: str = Field(min_length=1)
    samples: list[EvaluationSample] = Field(min_length=1)
    step: float = Field(default=0.05, gt=0, le=1)
    minimum_accept: float = Field(default=0.5, ge=0, le=1)
    minimum_clarification: float = Field(default=0.2, ge=0, le=1)

class ModelComparisonRequest(BaseModel):
    project_id: str = Field(min_length=1)
    model_ids: list[str] = Field(min_length=1)
    require_regression_pass: bool = False
    intent_f1_weight: float = Field(default=0.5, ge=0)
    entity_f1_weight: float = Field(default=0.3, ge=0)
    fallback_weight: float = Field(default=0.2, ge=0)

class ModelRuntimeServeRequest(BaseModel):
    project_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ModelVersionCreate(BaseModel):
    model_id: str | None = None
    version: str = Field(min_length=1, max_length=64)
    dataset_id: str = Field(min_length=1)
    dataset_version: str | None = None
    provider: str = "rasa"
    artifact_uri: str = Field(min_length=1)
    artifact_checksum: str | None = None
    training_job_id: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ModelDeploymentRequest(BaseModel):
    project_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    environment: str = Field(default="production", pattern="^(development|staging|production)$")
    canary: bool = False
    human_approved: bool = False
    auto_deploy: bool = False

class DeploymentCreate(BaseModel):
    project_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    canary: bool = False

class APIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    data: dict | None
    error: dict | None
    request_id: str | None = None


class InteractionCollect(BaseModel):
    project_id: str = Field(min_length=1)
    session_id: str | None = None
    language: str = Field(default="ar", min_length=2, max_length=32)
    input: str = Field(min_length=1, max_length=20000)
    predicted_intent: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    response: str | None = Field(default=None, max_length=20000)
    model_version: str | None = None
    processing_time: float | None = Field(default=None, ge=0)
    status: str = "completed"
    metadata: dict[str, Any] = Field(default_factory=dict)

class CandidateCreate(BaseModel):
    project_id: str = Field(min_length=1)
    interaction_id: str = Field(min_length=1)
    suggested_intent: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    quality_score: float | None = Field(default=None, ge=0, le=100)

class CandidateTransition(BaseModel):
    project_id: str = Field(min_length=1)
    status: str = Field(pattern="^(pending|reviewing|approved|rejected|duplicate)$")
    sample_status: str = Field(pattern="^(collected|filtered|pending_review|approved|rejected|promoted)$")


class ReviewCreate(BaseModel):
    project_id: str = Field(min_length=1)
    sample_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    decision: str = Field(pattern="^(approve|reject|correct)$")
    corrected_intent: str | None = None
    corrected_entities: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = Field(default="", max_length=10000)
    context: dict[str, Any] = Field(default_factory=dict)

class ConflictResolve(BaseModel):
    project_id: str = Field(min_length=1)
    resolver_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    policy: str = Field(default="senior_reviewer", pattern="^(senior_reviewer|consensus|rule)$")


class FeedbackCreate(BaseModel):
    project_id: str = Field(min_length=1)
    interaction_id: str = Field(min_length=1)
    type: str = Field(pattern="^(thumb_up|thumb_down|correction|explicit_intent|human_review)$")
    intent: str | None = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "user"
    trusted: bool = False
