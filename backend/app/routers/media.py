import re
import uuid
from urllib.parse import urlparse

from app import storage
from app.db import get_session
from app.deps import can_view_video
from app.models import User, Video
from app.security import decode_media_token
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/media", tags=["media"])
MEDIA_RE = re.compile(
    r"^/media/(?P<vid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
    r"(?P<rest>thumb\.jpg|hls/[A-Za-z0-9_][A-Za-z0-9_./-]*)$"
)


def parse_media_uri(uri):
    path = uri.split("?", 1)[0]
    m = MEDIA_RE.match(path)

    if not m or ".." in path or "//" in path:
        return None

    return uuid.UUID(m["vid"]), f"videos/{m['vid']}/{m['rest']}"


@router.get("/auth", include_in_schema=False)
async def media_auth(
    x_original_uri: str = Header(default=""),
    media_token: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
):
    parsed = parse_media_uri(x_original_uri)

    if not parsed:
        raise HTTPException(403, "Forbidden")

    video_id, key = parsed
    video = await session.get(Video, video_id)

    if not video:
        raise HTTPException(403, "Forbidden")

    user = None

    if media_token and (uid := decode_media_token(media_token)):
        u = await session.get(User, uid)

        if u and u.is_active:
            user = u

    if not await can_view_video(session, video, user):
        raise HTTPException(403, "Forbidden")

    url = await run_in_threadpool(storage.presign_get, key)

    return Response(
        status_code=200,
        headers={"X-Presigned-Url": url, "X-Presigned-Host": urlparse(url).netloc},
    )
