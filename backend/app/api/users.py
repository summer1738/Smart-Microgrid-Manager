"""Administrative user listing for session-authenticated deployments."""

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
    result = await session.execute(select(User).order_by(User.id))
    rows = list(result.scalars().all())
    return [UserOut.model_validate(user) for user in rows]
