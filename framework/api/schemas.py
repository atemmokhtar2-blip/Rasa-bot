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

class ProjectCreate(BaseModel):
    owner_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

class APIKeyCreate(BaseModel):
    developer_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    permissions: set[str] = set()

class MessageCreate(BaseModel):
    project_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    chat_id: str | None = None
    channel: str = "api"
    text: str | None = Field(default=None, max_length=10000)

class TrainingExampleInput(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    intent: str = Field(min_length=1, max_length=255)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class DatasetCreate(BaseModel):
    project_id: str = Field(min_length=1)
    version: str = Field(min_length=1, max_length=64)
    schema_version: str = "1"
    examples: list[TrainingExampleInput]

class TrainingCreate(BaseModel):
    project_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    config_path: str = Field(min_length=1)
    output_dir: str = Field(min_length=1)

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
