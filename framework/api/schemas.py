from pydantic import BaseModel, ConfigDict, EmailStr, Field

class DeveloperCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr

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

class APIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    data: dict | None
    error: dict | None
    request_id: str | None = None
