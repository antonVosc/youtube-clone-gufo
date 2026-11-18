import uuid

from app.db import get_session
from app.deps import can_view_video, current_user, current_user_optional
from app.models import Channel, Playlist, PlaylistItem, User, Video, Visibility
from app.schemas import PlaylistIn, PlaylistItemIn, PlaylistOut
from app.services.videos import to_out, video_query
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


async def _own(session: AsyncSession, playlist_id: uuid.UUID, user: User) -> Playlist:
    pl = await session.get(Playlist, playlist_id)
    ch = None

    if pl:
        ch = await session.get(Channel, pl.channel_id)

    if not pl or ch.owner_id != user.id:
        raise HTTPException(404, "Playlist not found")

    return pl


async def playlist_out(
    session: AsyncSession, pl: Playlist, user: User | None, with_videos=True
):
    ch = await session.get(Channel, pl.channel_id)
    videos = []

    if with_videos:
        q = (
            video_query()
            .join(PlaylistItem, PlaylistItem.video_id == Video.id)
            .where(PlaylistItem.playlist_id == pl.id)
            .order_by(PlaylistItem.position)
        )

        for v, lk, dl in (await session.execute(q)).all():
            if await can_view_video(session, v, user):
                videos.append(to_out(v, lk, dl))

    return PlaylistOut(
        id=pl.id,
        title=pl.title,
        visibility=pl.visibility,
        channel_handle=ch.handle,
        videos=videos,
    )


@router.post("", response_model=PlaylistOut, status_code=201)
async def create_playlist(
    data: PlaylistIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    ch = (
        await session.execute(select(Channel).where(Channel.owner_id == user.id))
    ).scalar_one()
    pl = Playlist(channel_id=ch.id, title=data.title, visibility=data.visibility)

    session.add(pl)
    await session.commit()

    return await playlist_out(session, pl, user)


@router.get("/{playlist_id}", response_model=PlaylistOut)
async def get_playlist(
    playlist_id: uuid.UUID,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    pl = await session.get(Playlist, playlist_id)

    if not pl:
        raise HTTPException(404, "Playlist not found")

    ch = await session.get(Channel, pl.channel_id)

    if pl.visibility == Visibility.private and not (user and ch.owner_id == user.id):
        raise HTTPException(404, "Playlist not found")

    return await playlist_out(session, pl, user)


@router.post("/{playlist_id}/items", response_model=PlaylistOut)
async def add_item(
    playlist_id: uuid.UUID,
    data: PlaylistItemIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    pl = await _own(session, playlist_id, user)
    v = await session.get(Video, data.video_id)

    if not v or not await can_view_video(session, v, user):
        raise HTTPException(404, "Video not found")

    if await session.get(PlaylistItem, (pl.id, v.id)):
        return await playlist_out(session, pl, user)

    pos = (
        await session.execute(
            select(func.coalesce(func.max(PlaylistItem.position), 0)).where(
                PlaylistItem.playlist_id == pl.id
            )
        )
    ).scalar_one() + 1
    session.add(PlaylistItem(playlist_id=pl.id, video_id=v.id, position=pos))
    await session.commit()

    return await playlist_out(session, pl, user)


@router.delete("/{playlist_id}/items/{video_id}", status_code=204)
async def remove_item(
    playlist_id: uuid.UUID,
    video_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    pl = await _own(session, playlist_id, user)
    item = await session.get(PlaylistItem, (pl.id, video_id))

    if item:
        await session.delete(item)
        await session.commit()


@router.delete("/{playlist_id}", status_code=204)
async def delete_playlist(
    playlist_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    pl = await _own(session, playlist_id, user)
    await session.delete(pl)
    await session.commit()
