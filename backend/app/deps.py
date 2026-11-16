from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Role, User
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


def client_ip(request):
    fwd = request.headers.get("x-forwarded-for")

    if fwd:
        return fwd.split(",")[0].strip()

    return request.client.host if request.client else "unknown"
