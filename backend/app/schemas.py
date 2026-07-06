import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    tenant_slug: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9-]+$")
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    tenant_slug: str
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LinkCreate(BaseModel):
    target_url: str = Field(max_length=2048)
    code: str | None = Field(default=None, min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")


class LinkResponse(BaseModel):
    id: uuid.UUID
    code: str
    target_url: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
