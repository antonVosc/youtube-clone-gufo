import math
import uuid

from app import ratelimit, services_queue, storage
from app.config import settings
from app.db import get_session
from app.deps import (
    can_view_video,
    client_ip,
    current_user,
    current_user_optional,
    get_video_or_404,
)
from app.models import Channel, Role, User, Video, VideoLike, VideoShare, VideoStatus
from app.schemas import (
    LikeIn,
    LikeOut,
    ShareIn,
    UploadCompleteIn,
    VideoCreateIn,
    VideoCreateOut,
    VideoOut,
    VideoPatch,
)
from app.services.videos import detail_out, to_out, video_query
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api", tags=["videos"])

ALLOWED_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska"}
MP4_BOXES = {b"ftyp", b"moov", b"wide", b"mdat", b"free", b"skip"}


def _looks_like_video(head):
    return head[:4] == b"\x1a\x45\xdf\xa3" or head[4:8] in MP4_BOXES


def _owned(video, user):
    if video.channel.owner_id != user.id:
        raise HTTPException(404, "Video not found")


async def _viewable(session, video_id: uuid.UUID, user: User | None) -> Video:
    v = await get_video_or_404(session, video_id)

    if not await can_view_video(session, v, user):
        raise HTTPException(404, "Video not found")

    return v


@router.post("/videos", response_model=VideoCreateOut, status_code=201)
async def create_video(
    data: VideoCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if data.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported video type")

    if data.size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")

    channel = (
        await session.execute(select(Channel).where(Channel.owner_id == user.id))
    ).scalar_one()

    vid = uuid.uuid4()
    key = f"videos/{vid}/source"
    upload_id = await run_in_threadpool(storage.start_multipart, key, data.content_type)

    session.add(
        Video(
            id=vid,
            channel_id=channel.id,
            title=data.title,
            description=data.description,
            visibility=data.visibility,
            source_key=key,
            upload_id=upload_id,
            size_bytes=data.size_bytes,
        )
    )
    await session.commit()
    parts = math.ceil(data.size_bytes / storage.PART_SIZE)

    return VideoCreateOut(
        video_id=vid,
        upload_id=upload_id,
        part_size=storage.PART_SIZE,
        part_urls=[
            storage.presign_part(key, upload_id, n) for n in range(1, parts + 1)
        ],
    )


@router.post("/videos/{video_id}/upload/complete", response_model=VideoOut)
async def complete_upload(
    video_id: uuid.UUID,
    data: UploadCompleteIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    v = await get_video_or_404(session, video_id)
    _owned(v, user)

    if v.status != VideoStatus.uploading or not v.upload_id:
        raise HTTPException(409, "Upload is not in progress")

    numbers = [p.part_number for p in data.parts]
    expected = math.ceil(v.size_bytes / storage.PART_SIZE)

    if sorted(numbers) != list(range(1, expected + 1)):
        raise HTTPException(400, "Parts do not match the upload plan")

    parts = sorted(
        ({"PartNumber": p.part_number, "ETag": p.etag} for p in data.parts),
        key=lambda p: p["PartNumber"],
    )

    try:
        await run_in_threadpool(
            storage.complete_multipart, v.source_key, v.upload_id, parts
        )
    except Exception:
        raise HTTPException(400, "Upload is incomplete or corrupted") from None

    v.upload_id = None
    head = await run_in_threadpool(storage.read_head, v.source_key)
    size = await run_in_threadpool(storage.head_size, v.source_key)

    if not _looks_like_video(head) or size > settings.max_upload_mb * 1024 * 1024:
        await run_in_threadpool(storage.delete_prefix, f"videos/{v.id}/")
        v.status, v.error = VideoStatus.failed, "Unsupported or oversized file"
        await session.commit()
        raise HTTPException(422, "File is not a valid video")

    v.size_bytes = size
    v.status = VideoStatus.processing

    await session.commit()
    services_queue.enqueue_transcode(str(v.id))

    return to_out(v)


@router.get("/me/videos", response_model=list[VideoOut])
async def my_videos(user=Depends(current_user), session=Depends(get_session)):
    q = (
        video_query()
        .join(Channel, Video.channel_id == Channel.id)
        .where(Channel.owner_id == user.id)
        .order_by(Video.created_at.desc())
    )

    return [to_out(v, lk, dl) for v, lk, dl in (await session.execute(q)).all()]


@router.get("/videos/{video_id}", response_model=VideoOut)
async def get_video(
    video_id: uuid.UUID,
    user: User | None = Depends(current_user_optional),
    session=Depends(get_session),
):
    await _viewable(session, video_id, user)
    return await detail_out(session, video_id, user)


@router.patch("/videos/{video_id}", response_model=VideoOut)
async def patch_video(
    video_id: uuid.UUID,
    data: VideoPatch,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    v = await get_video_or_404(session, video_id)
    _owned(v, user)

    for k, val in data.model_dump(exclude_none=True).items():
        setattr(v, k, val)

    await session.commit()
    return await detail_out(session, video_id, user)


@router.delete("/videos/{video_id}", status_code=204)
async def delete_video(
    video_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    v = await get_video_or_404(session, video_id)

    if v.channel.owner_id != user.id and user.role != Role.admin:
        raise HTTPException(404, "Video not found")

    if v.status == VideoStatus.uploading and v.upload_id:
        try:
            await run_in_threadpool(storage.abort_multipart, v.source_key, v.upload_id)
        except Exception:
            pass

    await run_in_threadpool(storage.delete_prefix, f"videos/{v.id}/")
    await session.delete(v)
    await session.commit()


@router.post("/videos/{video_id}/view", status_code=204)
async def count_view(
    video_id: uuid.UUID,
    request: Request,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    ratelimit.check(f"view:{client_ip(request)}:{video_id}", 3, 60)
    v = await _viewable(session, video_id, user)

    if v.status == VideoStatus.ready:
        await session.execute(
            update(Video)
            .where(Video.id == v.id)
            .values(views_count=Video.views_count + 1)
        )

        await session.commit()


@router.put("/videos/{video_id}/like", response_model=LikeOut)
async def like_video(
    video_id: uuid.UUID,
    data: LikeIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    await _viewable(session, video_id, user)

    if data.value == 0:
        row = await session.get(VideoLike, (video_id, user.id))

        if row:
            await session.delete(row)
    else:
        stmt = insert(VideoLike).values(
            video_id=video_id, user_id=user.id, value=data.value
        )

        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[VideoLike.video_id, VideoLike.user_id],
                set_={"value": data.value},
            )
        )

    await session.commit()
    out = await detail_out(session, video_id, user)

    return LikeOut(likes=out.likes, dislikes=out.dislikes, my_like=out.my_like)


@router.get("/videos/{video_id}/shares", response_model=list[str])
async def list_shares(
    video_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    v = await get_video_or_404(session, video_id)
    _owned(v, user)
    q = (
        select(User.username)
        .join(VideoShare, VideoShare.user_id == User.id)
        .where(VideoShare.video_id == v.id)
    )

    return sorted((await session.execute(q)).scalars().all())


@router.post("/videos/{video_id}/shares", status_code=204)
async def share_video(
    video_id: uuid.UUID,
    data: ShareIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    v = await get_video_or_404(session, video_id)
    _owned(v, user)
    target = (
        await session.execute(select(User).where(User.username == data.username))
    ).scalar_one_or_none()

    if not target:
        raise HTTPException(404, "User not found")

    await session.execute(
        insert(VideoShare)
        .values(video_id=v.id, user_id=target.id)
        .on_conflict_do_nothing()
    )

    await session.commit()


@router.delete("/videos/{video_id}/shares/{username}", status_code=204)
async def unshare_video(
    video_id: uuid.UUID,
    username: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    v = await get_video_or_404(session, video_id)
    _owned(v, user)
    target = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()

    if target and (share := await session.get(VideoShare, (v.id, target.id))):
        await session.delete(share)
        await session.commit()
