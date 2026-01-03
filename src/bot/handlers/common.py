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
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        # 1. User jismonan bazada bormi? (Hal qiluvchi)
        user_in_db = user is not None

        # 2. Rolini aniqlash
        if user_id in settings.ADMIN_IDS:
            role_key = "super_admin"
            welcome_text = f"🛡 **Super Admin paneliga xush kelibsiz!**"
        elif user:
            role_key = user.role.value
            welcome_text = f"🚀 **Siz tizimga {role_key} sifatida kirdingiz.**"
        else:
            role_key = None
            welcome_text = "❌ <b>Siz ro'yxatdan o'tmagansiz.</b>\nIltimos, administratorga ID raqamingizni yuboring: \n\n🆔 ID: <code>{}</code>".format(user_id)

    # Rejim
    if role_key in ["super_admin", "admin", "super_employee"]:
        mode = "admin"
    else:
        mode = "employee"

    # Dinamik menyu
    await message.answer(welcome_text, reply_markup=get_main_menu(role_key, mode=mode, user_in_db=user_in_db), parse_mode="HTML")

@router.message(F.text == "👤 Xodim rejimiga o'tish")
async def switch_to_employee(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        user_in_db = user is not None
        
        # Agar user bazada bo'lmasa, demak xodim ham emas
        if not user_in_db:
             # Super admin bo'lsa, menyusi qaytib kelsin, lekin xodim rejimi yo'q
            role = "super_admin" if user_id in settings.ADMIN_IDS else None
            return await message.answer("❌ Siz xodimlar ro'yxatida yo'qsiz.", reply_markup=get_main_menu(role, mode="admin", user_in_db=False))

        role = "super_admin" if user_id in settings.ADMIN_IDS else user.role.value
        await message.answer("🔄 **Xodim rejimiga o'tdingiz.**", reply_markup=get_main_menu(role, mode="employee", user_in_db=user_in_db), parse_mode="Markdown")

@router.message(F.text == "⚙️ Admin rejimiga o'tish")
async def switch_to_admin(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        user_in_db = user is not None

        is_admin = user_id in settings.ADMIN_IDS or (user and user.role in [UserRole.admin, UserRole.super_employee])
        
        if is_admin:
            role = "super_admin" if user_id in settings.ADMIN_IDS else user.role.value
            await message.answer("🔄 **Admin rejimiga qaytdingiz.**", reply_markup=get_main_menu(role, mode="admin", user_in_db=user_in_db), parse_mode="Markdown")
        else:
            await message.answer("⛔️ Sizda adminlik huquqi yo'q.")