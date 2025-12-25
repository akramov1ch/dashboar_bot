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
    """Botni ishga tushirish va foydalanuvchini aniqlash"""
    user_id = message.from_user.id
    full_name = message.from_user.full_name

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()

        # 1. Super Admin tekshiruvi (Agar bazada bo'lmasa, avtomatik qo'shish)
        if user_id in settings.ADMIN_IDS:
            role_key = "super_admin"
            if not user:
                user = User(
                    telegram_id=user_id,
                    full_name=full_name,
                    role=UserRole.admin, # Kichik harf bazaga mos
                    personal_sheet_id=settings.DEFAULT_SPREADSHEET_ID
                )
                session.add(user)
                await session.commit()
            welcome_text = f"🛡 **Super Admin paneliga xush kelibsiz, {full_name}!**"
        
        # 2. Bazadagi foydalanuvchilar uchun rollarni aniqlash
        elif user:
            role_key = user.role.value # 'admin', 'super_employee', 'employee'
            if user.role == UserRole.super_employee:
                welcome_text = f"🚀 **Super Employee paneliga xush kelibsiz, {full_name}!**\nSiz ham vazifa bera olasiz, ham o'z vazifalaringizni ko'ra olasiz."
            elif user.role == UserRole.admin:
                welcome_text = f"👨‍💻 **Admin paneliga xush kelibsiz, {full_name}!**"
            else:
                welcome_text = f"👋 **Salom, {full_name}!**"
        
        # 3. Ro'yxatdan o'tmaganlar
        else:
            role_key = "employee"
            welcome_text = "❌ **Siz tizimda ro'yxatdan o'tmagansiz.**\nIltimos, Adminlar tomonidan qo'shilishingizni kuting."

    # Admin huquqi borlar uchun birinchi bo'lib Admin menyusini chiqaramiz
    mode = "admin" if role_key in ["super_admin", "admin", "super_employee"] else "employee"
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu(role_key, mode=mode),
        parse_mode="Markdown"
    )

# =====================================================================
# REJIMLARNI ALMASHTIRISH MANTIQI
# =====================================================================

@router.message(F.text == "👤 Xodim rejimiga o'tish")
async def switch_to_employee(message: types.Message):
    """Adminlik huquqi bor foydalanuvchini Xodim rejimiga o'tkazish"""
    user_id = message.from_user.id
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        # Rolni aniqlash
        if user_id in settings.ADMIN_IDS:
            role_key = "super_admin"
        elif user:
            role_key = user.role.value
        else:
            role_key = "employee"

        await message.answer(
            "🔄 **Xodim rejimiga o'tdingiz.**\nEndi o'z vazifalaringizni ko'rishingiz va statusni yangilashingiz mumkin.", 
            reply_markup=get_main_menu(role_key, mode="employee"),
            parse_mode="Markdown"
        )

@router.message(F.text == "⚙️ Admin rejimiga o'tish")
async def switch_to_admin(message: types.Message):
    """Xodim rejimidan Admin rejimiga qaytish"""
    user_id = message.from_user.id
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        # Faqat adminlik huquqi borlar o'ta oladi
        is_admin = user_id in settings.ADMIN_IDS or (user and user.role in [UserRole.admin, UserRole.super_employee])
        
        if is_admin:
            role_key = "super_admin" if user_id in settings.ADMIN_IDS else user.role.value
            await message.answer(
                "🔄 **Admin rejimiga qaytdingiz.**\nBoshqaruv paneli tayyor.", 
                reply_markup=get_main_menu(role_key, mode="admin"),
                parse_mode="Markdown"
            )
        else:
            await message.answer("⛔️ **Sizda adminlik huquqi yo'q!**")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "❓ **Botdan foydalanish bo'yicha yordam:**\n\n"
        "1. **Admin rejimi:** Vazifa qo'shish, xodim qo'shish va hisobotlarni ko'rish.\n"
        "2. **Xodim rejimi:** Sizga berilgan vazifalarni ko'rish va ularni 'Bajarildi' deb belgilash.\n"
        "3. **Rejimni almashtirish:** Menyuning eng pastidagi tugma orqali amalga oshiriladi."
    )
    await message.answer(help_text, parse_mode="Markdown")