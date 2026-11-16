from datetime import datetime, timedelta, timezone

from app import ratelimit
from app.config import settings
from app.db import get_session
from app.deps import client_ip, current_user
from app.models import Channel, RefreshToken, User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import (
    create_access_token,
    create_media_token,
    hash_password,
    hash_refresh,
    new_refresh_token,
    verify_password,
)
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE = "refresh_token"
_DUMMY = hash_password("test-password")
MEDIA_COOKIE = "media_token"


def _set_cookies(resp: Response, raw, user_id):
    resp.set_cookie(
        COOKIE,
        raw,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/api/auth",
        max_age=settings.refresh_ttl_days * 86400,
    )

    resp.set_cookie(
        MEDIA_COOKIE,
        create_media_token(user_id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/media/",
        max_age=settings.media_ttl_min * 60,
    )


async def _issue(session, user, resp):
    raw, h = new_refresh_token()

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=h,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_ttl_days),
        )
    )

    await session.commit()

    _set_cookies(resp, raw, user.id)

    return TokenOut(access_token=create_access_token(user.id))


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    data: RegisterIn, request: Request, session: AsyncSession = Depends(get_session)
):
    ratelimit.check(f"reg:{client_ip(request)}", 10, 3600)

    user = User(
        email=data.email.lower(),
        username=data.username,
        password_hash=hash_password(data.password),
    )

    session.add(user)
    try:
        await session.flush()

        session.add(
            Channel(owner_id=user.id, handle=data.username.lower(), name=data.username)
        )

        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Email or username already taken") from None

    return user


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, request, response, session=Depends(get_session)):
    email = data.email.lower()
    ratelimit.check(f"login:{client_ip(request)}:{email}", 10, 300)

    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    ok = verify_password(data.password, user.password_hash if user else _DUMMY)

    if not user or not ok or not user.is_active:
        raise HTTPException(401, "Invalid credentials")

    return await _issue(session, user, response)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    response, refresh_token=Cookie(default=None), session=Depends(get_session)
):
    if not refresh_token:
        raise HTTPException(401, "No refresh token")
    rt = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh(refresh_token)
            )
        )
    ).scalar_one_or_none()

    if not rt or rt.revoked or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, "Invalid refresh token")

    user = await session.get(User, rt.user_id)

    if not user or not user.is_active:
        raise HTTPException(401, "Invalid refresh token")

    rt.revoked = True

    return await _issue(session, user, response)


@router.post("/logout", status_code=204)
async def logout(
    response, refresh_token=Cookie(default=None), session=Depends(get_session)
):
    if refresh_token:
        rt = (
            await session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == hash_refresh(refresh_token)
                )
            )
        ).scalar_one_or_none()

        if rt:
            rt.revoked = True

            await session.commit()

    response.delete_cookie(COOKIE, path="/api/auth")
    response.delete_cookie(MEDIA_COOKIE, path="/media/")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user
