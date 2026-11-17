import uuid
from datetime import datetime
from xml.dom.minicompat import NodeList

from pydantic import BaseModel, ConfigDict, Field

from app.models import Role, VideoStatus, Visibility


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


class VideoCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=5000)
    visibility: Visibility = Visibility.public
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)


class VideoCreateOut(BaseModel):
    video_id: uuid.UUID
    upload_id: str
    part_size: int
    part_urls: list[str]


class UploadPart(BaseModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str


class UploadCompleteIn(BaseModel):
    parts: list[UploadPart] = Field(min_length=1)


class VideoPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Visibility | None = None


class VideoOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    status: VideoStatus
    visibility: Visibility
    is_hidden: bool = False
    duration_sec: int | None = None
    views_count: int = 0
    created_at: datetime
    thumb_url: str | None = None
    hls_url: str | None = None
    likes: int = 0
    dislikes: int = 0
    my_like: int = 0


class ShareIn(BaseModel):
    username: str
