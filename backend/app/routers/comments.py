import uuid

from app import ratelimit
from app.db import get_session
from app.deps import (
    STAFF,
    can_view_video,
    current_user,
    current_user_optional,
    get_video_or_404,
)
from app.models import Comment, User
from app.schemas import CommentIn, CommentOut
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["comments"])


async def _visible_video(session, video_id, user):
    v = await get_video_or_404(session, video_id)

    if not await can_view_video(session, v, user):
        raise HTTPException(404, "Video not found")

    return v


@router.get("/videos/{video_id}/comments", response_model=list[CommentOut])
async def list_comments(
    video_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    await _visible_video(session, video_id, user)

    q = (
        select(Comment, User.username)
        .join(User, User.id == Comment.user_id)
        .where(Comment.video_id == video_id)
        .order_by(Comment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return [
        CommentOut(
            id=c.id,
            video_id=c.video_id,
            username=name,
            parent_id=c.parent_id,
            text=c.text,
            created_at=c.created_at,
        )
        for c, name in (await session.execute(q)).all()
    ]


@router.post("/videos/{video_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    video_id: uuid.UUID,
    data: CommentIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    ratelimit.check(f"comment:{user.id}", 20, 60)
    await _visible_video(session, video_id, user)
    text = data.text.strip()

    if not text:
        raise HTTPException(422, "Empty comment")

    if data.parent_id:
        parent = await session.get(Comment, data.parent_id)

        if not parent or parent.video_id != video_id:
            raise HTTPException(404, "Parent comment not found")

    c = Comment(video_id=video_id, user_id=user.id, parent_id=data.parent_id, text=text)
    session.add(c)

    await session.commit()
    await session.refresh(c)

    return CommentOut(
        id=c.id,
        video_id=c.video_id,
        username=user.username,
        parent_id=c.parent_id,
        text=c.text,
        created_at=c.created_at,
    )


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    c = await session.get(Comment, comment_id)

    if not c:
        raise HTTPException(404, "Comment not found")

    if c.user_id != user.id and user.role not in STAFF:
        raise HTTPException(403, "Not allowed")

    await session.delete(c)
    await session.commit()
