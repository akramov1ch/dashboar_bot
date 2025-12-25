from aiogram.filters import BaseFilter
from aiogram.types import Message
from src.database.models import User, UserRole
from sqlalchemy import select
from src.database.base import async_session

class RoleFilter(BaseFilter):
    def __init__(self, role: UserRole):
        self.role = role

    async def __call__(self, message: Message) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            return user is not None and user.role == self.role