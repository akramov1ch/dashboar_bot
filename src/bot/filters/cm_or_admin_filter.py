# src/bot/filters/cm_or_admin_filter.py

from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy import select

from src.config import settings
from src.database.base import async_session
from src.database.models import User, UserRole


class IsContentMakerOrAdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False

        tid = message.from_user.id

        # Super admin
        if tid in settings.ADMIN_IDS:
            return True

        # DB role check
        async with async_session() as session:
            res = await session.execute(select(User).where(User.telegram_id == tid))
            user = res.scalar_one_or_none()
            if not user:
                return False

            return user.role in {UserRole.admin, UserRole.content_maker}