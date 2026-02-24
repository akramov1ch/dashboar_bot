# src/bot/filters/admin_filter.py

from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy import select

from src.config import settings
from src.database.base import async_session
from src.database.models import User, UserRole


class IsAnyAdminFilter(BaseFilter):
    """
    Admin tekshiruv filtri.

    Admin hisoblanadi:
    1) settings.ADMIN_IDS ro'yxatida bo'lgan (Super Admin)
    2) Bazada roli UserRole.admin bo'lgan foydalanuvchi

    Eslatma:
    - super_employee kabi mavjud bo'lmagan enum ishlatilmaydi.
    - Faqat aniq UserRole.admin tekshiriladi.
    """

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False

        telegram_id = message.from_user.id

        # 1. Super Admin (config orqali)
        if telegram_id in settings.ADMIN_IDS:
            return True

        # 2. Bazadagi admin roli
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                return False

            return user.role == UserRole.admin