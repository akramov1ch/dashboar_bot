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
        
        user_in_db = user is not None

        # 1. Super Admin tekshiruvi (settings.py dagi IDlar)
        if user_id in settings.ADMIN_IDS:
            role_key = "admin"
            welcome_text = f"🛡 **Super Admin paneliga xush kelibsiz!**"
        # 2. Bazadagi ro'yxatdan o'tgan xodimlar
        elif user:
            role_key = user.role.value
            welcome_text = f"🚀 **Siz tizimga {role_key} sifatida kirdingiz.**"
        # 3. Ro'yxatdan o'tmaganlar
        else:
            role_key = None
            welcome_text = (
                "❌ <b>Siz ro'yxatdan o'tmagansiz.</b>\n"
                "Iltimos, administratorga ID raqamingizni yuboring: \n\n"
                "🆔 ID: <code>{}</code>".format(user_id)
            )

    # get_main_menu funksiyasidan 'mode' argumenti olib tashlandi ✅
    await message.answer(
        welcome_text, 
        reply_markup=get_main_menu(role_key, user_in_db=user_in_db), 
        parse_mode="HTML"
    )

@router.message(F.text == "👤 Ijrochi rejimiga o'tish")
async def switch_to_employee(message: types.Message):
    user_id = message.from_user.id
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        
        if not user:
            return await message.answer("❌ Siz xodimlar ro'yxatida yo'qsiz.")

        await message.answer(
            "🔄 **Ijrochi rejimiga o'tdingiz.**", 
            reply_markup=get_main_menu(user.role.value, user_in_db=True), 
            parse_mode="Markdown"
        )