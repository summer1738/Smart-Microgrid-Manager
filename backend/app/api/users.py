"""Read-only user list for UI role selection (demo auth; not a replacement for real login)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_min_role
from app.database import get_db
from app.models import User
from app.schemas import UserOut

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_min_role("admin"))],
)


@router.get("", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_db)) -> list[UserOut]:
    r = await session.execute(select(User).order_by(User.id))
    rows = list(r.scalars().all())
    return [UserOut.model_validate(u) for u in rows]
