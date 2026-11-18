from app.db import get_session
from app.deps import current_user
from app.models import Subscription, User, Video
from app.schemas import VideoOut
from app.services.videos import list_out, public_filter
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["feed"])


@router.get("/feed", response_model=list[VideoOut])
async def feed(
    limit=Query(24, ge=1, le=50),
    offset=Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await list_out(session, public_filter(), limit, offset)


@router.get("/feed/subscriptions", response_model=list[VideoOut])
async def subscriptions_feed(
    limit=Query(24, ge=1, le=50),
    offset=Query(0, ge=0),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    subs = select(Subscription.channel_id).where(Subscription.subscriber_id == user.id)

    return await list_out(
        session, public_filter() & Video.channel_id.in_(subs), limit, offset
    )


@router.get("/search", response_model=list[VideoOut])
async def search(
    q=Query(min_length=1, max_length=100),
    limit=Query(24, ge=1, le=50),
    offset=Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    fts = func.to_tsvector("simple", Video.title).op("@@")(
        func.plainto_tsquery("simple", q)
    )

    cond = or_(fts, Video.title.ilike(f"%{esc}%", escape="\\"))

    return await list_out(session, public_filter() & cond, limit, offset)
