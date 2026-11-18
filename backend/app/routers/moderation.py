import uuid

from app.db import get_session
from app.deps import can_view_video, current_user, get_video_or_404, require_role
from app.models import Report, ReportStatus, Role, User, Video
from app.schemas import HideIn, ReportIn, ReportOut, ResolveIn, VideoOut
from app.services.videos import to_out, video_query
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["moderation"])
staff = require_role(Role.moderator, Role.admin)


@router.post("/videos/{video_id}/report", status_code=201)
async def report_video(
    video_id: uuid.UUID,
    data: ReportIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    v = await get_video_or_404(session, video_id)

    if not await can_view_video(session, v, user):
        raise HTTPException(404, "Video not found")

    if v.channel.owner_id == user.id:
        raise HTTPException(400, "You cannot report your own video")

    dup = (
        await session.execute(
            select(Report).where(Report.video_id == v.id, Report.reporter_id == user.id)
        )
    ).scalar_one_or_none()

    if dup:
        raise HTTPException(409, "You already reported this video")

    session.add(Report(video_id=v.id, reporter_id=user.id, reason=data.reason))
    await session.commit()

    return {"status": "ok"}


@router.get("/moderation/reports", response_model=list[ReportOut])
async def list_reports(
    status: ReportStatus = ReportStatus.open,
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
):
    q = (
        select(Report, Video, User.username)
        .join(Video, Video.id == Report.video_id)
        .join(User, User.id == Report.reporter_id)
        .where(Report.status == status)
        .order_by(Report.created_at.desc())
        .limit(limit)
    )

    return [
        ReportOut(
            id=r.id,
            video_id=v.id,
            video_title=v.title,
            video_is_hidden=v.is_hidden,
            channel_handle=v.channel.handle,
            reporter=name,
            reason=r.reason,
            status=r.status.value,
            created_at=r.created_at,
        )
        for r, v, name in (await session.execute(q)).all()
    ]


@router.get("/moderation/hidden", response_model=list[VideoOut])
async def hidden_videos(
    _: User = Depends(staff), session: AsyncSession = Depends(get_session)
):
    q = video_query().where(Video.is_hidden.is_(True)).order_by(Video.created_at.desc())

    return [to_out(v, lk, dl) for v, lk, dl in (await session.execute(q)).all()]


async def _set_hidden(
    session: AsyncSession, video_id: uuid.UUID, hidden: bool, reason: str | None
):
    v = await get_video_or_404(session, video_id)

    v.is_hidden = hidden
    v.hidden_reason = None

    if hidden:
        v.hidden_reason = reason

    await session.commit()


@router.post("/moderation/videos/{video_id}/hide", status_code=204)
async def hide(
    video_id: uuid.UUID,
    data: HideIn,
    _: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
):
    await _set_hidden(session, video_id, True, data.reason)


@router.post("/moderation/videos/{video_id}/unhide", status_code=204)
async def unhide(
    video_id: uuid.UUID,
    _: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
):
    await _set_hidden(session, video_id, False, None)


@router.post("/moderation/reports/{report_id}/resolve", status_code=204)
async def resolve(
    report_id: uuid.UUID,
    data: ResolveIn,
    mod: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
):
    r = await session.get(Report, report_id)

    if not r:
        raise HTTPException(404, "Report not found")

    if data.action == "hide":
        await _set_hidden(session, r.video_id, True, r.reason)
        await session.execute(
            update(Report)
            .where(Report.video_id == r.video_id, Report.status == ReportStatus.open)
            .values(status=ReportStatus.resolved, resolved_by=mod.id)
        )
    else:
        r.status, r.resolved_by = ReportStatus.dismissed, mod.id

    await session.commit()
