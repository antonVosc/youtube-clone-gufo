from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Role, User, Video, VideoShare, VideoStatus, Visibility
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)
STAFF = {Role.moderator, Role.admin}


async def current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
):
    if not creds:
        return None

    uid = decode_access_token(creds.credentials)

    if not uid:
        return None

    user = await session.get(User, uid)

    if user and user.is_active:
        return user

    return None


async def current_user(user=Depends(current_user_optional)):
    if not user:
        raise HTTPException(401, "Not authenticated")

    return user


def require_role(*roles: Role):
    async def dep(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Insufficient role")

        return user

    return dep


async def can_view_video(session, video, user: User | None):
    is_owner = bool(user and video.channel.owner_id == user.id)
    is_staff = bool(user and user.role in STAFF)

    if is_owner or is_staff:
        return True

    if video.is_hidden or video.status != VideoStatus.ready:
        return False

    if video.visibility in (Visibility.public, Visibility.unlisted):
        return True

    if user is None:
        return False

    shared = await session.execute(
        select(VideoShare).where(
            VideoShare.video_id == video.id, VideoShare.user_id == user.id
        )
    )

    return shared.scalar_one_or_none() is not None


async def get_video_or_404(session, video_id):
    v = await session.get(Video, video_id, options=[selectinload(Video.channel)])

    if not v:
        raise HTTPException(404, "Video not found")

    return v


def client_ip(request):
    fwd = request.headers.get("x-forwarded-for")

    if fwd:
        return fwd.split(",")[0].strip()

    return request.client.host if request.client else "unknown"
