import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Video, VideoLike, VideoStatus, Visibility
from app.schemas import ChannelBrief, VideoOut


def public_filter():
    return and_(
        Video.status == VideoStatus.ready,
        Video.visibility == Visibility.public,
        Video.is_hidden.is_(False),
    )


def _count(value):
    return (
        select(func.count())
        .select_from(VideoLike)
        .where(VideoLike.video_id == Video.id, VideoLike.value == value)
        .correlate(Video)
        .scalar_subquery()
    )


def video_query():
    return select(Video, _count(1).label("likes"), _count(-1).label("dislikes"))


def to_out(v: Video, likes=0, dislikes=0, my_like=0):
    ready = v.status == VideoStatus.ready
    t_url = None
    h_url = None

    if v.thumb_key:
        t_url = f"/media/{v.id}/thumb.jpg"

    if ready and v.hls_prefix:
        h_url = f"/media/{v.id}/hls/master.m3u8"

    return VideoOut(
        id=v.id,
        channel=ChannelBrief(handle=v.channel.handle, name=v.channel.name),
        title=v.title,
        description=v.description,
        status=v.status,
        visibility=v.visibility,
        is_hidden=v.is_hidden,
        duration_sec=v.duration_sec,
        views_count=v.views_count,
        created_at=v.created_at,
        thumb_url=t_url,
        hls_url=h_url,
        likes=likes,
        dislikes=dislikes,
        my_like=my_like,
    )


async def list_out(session: AsyncSession, where, limit=24, offset=0) -> list[VideoOut]:
    q = (
        video_query()
        .where(where)
        .order_by(Video.created_at.desc(), Video.id)
        .limit(limit)
        .offset(offset)
    )

    return [to_out(v, lk, dl) for v, lk, dl in (await session.execute(q)).all()]


async def detail_out(
    session: AsyncSession, video_id: uuid.UUID, user: User | None
) -> VideoOut:
    v, likes, dislikes = (
        await session.execute(video_query().where(Video.id == video_id))
    ).one()
    my = 0

    if user:
        row = await session.get(VideoLike, (video_id, user.id))

        if row:
            my = row.value

    return to_out(v, likes, dislikes, my)
