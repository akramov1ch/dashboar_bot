from aiogram.filters import BaseFilter
from aiogram.types import Message
from src.config import settings
from src.database.models import User, UserRole
from src.database.base import async_session
from sqlalchemy import select

class IsAnyAdminFilter(BaseFilter):
    """Super Admin yoki Oddiy Admin ekanligini tekshirish"""
    async def __call__(self, message: Message) -> bool:
        # 1. Super Admin tekshiruvi
        if message.from_user.id in settings.ADMIN_IDS:
            return True
        
        # 2. Oddiy Admin tekshiruvi
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            # Kichik harflarda yozamiz ✅
            return user is not None and user.role in [UserRole.admin, UserRole.super_employee]