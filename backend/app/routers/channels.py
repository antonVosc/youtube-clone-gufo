from app.db import get_session
from app.deps import current_user, current_user_optional
from app.models import Channel, Playlist, Subscription, User, Video, Visibility
from app.schemas import ChannelOut, ChannelPatch, PlaylistOut, VideoOut
from app.services.videos import list_out, public_filter, to_out, video_query
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/channels", tags=["channels"])


async def _out(session: AsyncSession, ch: Channel, user: User | None):
    n = (
        await session.execute(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.channel_id == ch.id)
        )
    ).scalar_one()

    sub = False

    if user:
        sub = (await session.get(Subscription, (user.id, ch.id))) is not None

    return ChannelOut(
        id=ch.id,
        handle=ch.handle,
        name=ch.name,
        description=ch.description,
        subscribers=n,
        subscribed=sub,
    )


async def _by_handle(session: AsyncSession, handle: str) -> Channel:
    ch = (
        await session.execute(select(Channel).where(Channel.handle == handle.lower()))
    ).scalar_one_or_none()

    if not ch:
        raise HTTPException(404, "Channel not found")

    return ch


@router.patch("/me", response_model=ChannelOut)
async def patch_my_channel(
    data: ChannelPatch,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    ch = (
        await session.execute(select(Channel).where(Channel.owner_id == user.id))
    ).scalar_one()

    for k, v in data.model_dump(exclude_none=True).items():
        setattr(ch, k, v)

    await session.commit()

    return await _out(session, ch, user)


@router.get("/{handle}", response_model=ChannelOut)
async def get_channel(
    handle: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    return await _out(session, await _by_handle(session, handle), user)


@router.post("/{handle}/subscribe", response_model=ChannelOut)
async def subscribe(
    handle: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    ch = await _by_handle(session, handle)

    if ch.owner_id == user.id:
        raise HTTPException(400, "Cannot subscribe to your own channel")

    await session.execute(
        insert(Subscription)
        .values(subscriber_id=user.id, channel_id=ch.id)
        .on_conflict_do_nothing()
    )
    await session.commit()

    return await _out(session, ch, user)


@router.delete("/{handle}/subscribe", response_model=ChannelOut)
async def unsubscribe(
    handle: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    ch = await _by_handle(session, handle)
    sub = await session.get(Subscription, (user.id, ch.id))

    if sub:
        await session.delete(sub)
        await session.commit()

    return await _out(session, ch, user)


@router.get("/{handle}/videos", response_model=list[VideoOut])
async def channel_videos(
    handle: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    ch = await _by_handle(session, handle)

    if user and ch.owner_id == user.id:
        q = (
            video_query()
            .where(Video.channel_id == ch.id)
            .order_by(Video.created_at.desc())
        )

        return [to_out(v, lk, dl) for v, lk, dl in (await session.execute(q)).all()]

    return await list_out(
        session, public_filter() & (Video.channel_id == ch.id), limit=50
    )


@router.get("/{handle}/playlists", response_model=list[PlaylistOut])
async def channel_playlists(
    handle: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    ch = await _by_handle(session, handle)
    q = select(Playlist).where(Playlist.channel_id == ch.id).order_by(Playlist.title)

    if not (user and ch.owner_id == user.id):
        q = q.where(Playlist.visibility == Visibility.public)

    return [
        PlaylistOut(
            id=p.id, title=p.title, visibility=p.visibility, channel_handle=ch.handle
        )
        for p in (await session.execute(q)).scalars().all()
    ]
