from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select

from src.database.base import async_session
from src.database.models import User, UserRole
from src.bot.keyboards.reply import get_main_menu
from src.config import settings

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()

        if user_id in settings.ADMIN_IDS:
            role_key = "super_admin"
            if not user:
                user = User(
                    telegram_id=user_id,
                    full_name=full_name,
                    role=UserRole.admin, # Kichik harf ✅
                    personal_sheet_id=settings.DEFAULT_SPREADSHEET_ID
                )
                session.add(user)
                await session.commit()
            welcome_text = f"🛡 **Super Admin paneliga xush kelibsiz!**"
        elif user:
            role_key = user.role.value
            welcome_text = f"🚀 **Siz tizimga {role_key} sifatida kirdingiz.**"
        else:
            role_key = "employee"
            welcome_text = "❌ Ro'yxatdan o'tmagansiz."

    mode = "admin" if role_key in ["super_admin", "admin", "super_employee"] else "employee"
    await message.answer(welcome_text, reply_markup=get_main_menu(role_key, mode=mode), parse_mode="Markdown")

@router.message(F.text == "👤 Xodim rejimiga o'tish")
async def switch_to_employee(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        role = "super_admin" if user_id in settings.ADMIN_IDS else (user.role.value if user else "employee")
        await message.answer("🔄 **Xodim rejimiga o'tdingiz.**", reply_markup=get_main_menu(role, mode="employee"), parse_mode="Markdown")

@router.message(F.text == "⚙️ Admin rejimiga o'tish")
async def switch_to_admin(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        is_admin = user_id in settings.ADMIN_IDS or (user and user.role in [UserRole.admin, UserRole.super_employee])
        if is_admin:
            role = "super_admin" if user_id in settings.ADMIN_IDS else user.role.value
            await message.answer("🔄 **Admin rejimiga qaytdingiz.**", reply_markup=get_main_menu(role, mode="admin"), parse_mode="Markdown")
        else:
            await message.answer("⛔️ Sizda adminlik huquqi yo'q.")