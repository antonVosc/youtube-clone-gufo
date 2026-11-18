import uuid

from app.db import get_session
from app.deps import require_role
from app.models import Role, User
from app.schemas import ActiveIn, AdminUserOut, RoleIn, UserOut
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.put("/users/{user_id}/role", response_model=UserOut)
async def set_role(
    user_id: uuid.UUID,
    data: RoleIn,
    admin: User = Depends(require_role(Role.admin)),
    session: AsyncSession = Depends(get_session),
):
    if user_id == admin.id:
        raise HTTPException(400, "Cannot change your own role")

    user = await session.get(User, user_id)

    if not user:
        raise HTTPException(404, "User not found")

    user.role = data.role
    await session.commit()

    return user


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    _: User = Depends(require_role(Role.admin)),
    session: AsyncSession = Depends(get_session),
):
    return (
        (await session.execute(select(User).order_by(User.created_at))).scalars().all()
    )


@router.put("/users/{user_id}/active", response_model=AdminUserOut)
async def set_active(
    user_id: uuid.UUID,
    data: ActiveIn,
    admin: User = Depends(require_role(Role.admin)),
    session: AsyncSession = Depends(get_session),
):
    if user_id == admin.id:
        raise HTTPException(400, "Cannot deactivate yourself")

    user = await session.get(User, user_id)

    if not user:
        raise HTTPException(404, "User not found")

    user.is_active = data.active
    await session.commit()

    return user
