import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models import Role


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,40}$")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    username: str
    role: Role


class RoleIn(BaseModel):
    role: Role


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    handle: str
    name: str
    description: str
    subscribers: int = 0
    subscribed: bool = False


class ChannelPatch(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
