# src/bot/handlers/admin.py
#
# ✅ Designer olib tashlangan (rol tanlashda ham yo'q)
# ✅ Task approve/reject oqimi saqlangan
# ✅ Marketer link yuborganda admin tasdiqlaydi -> link AH(34) ga barcha ishtirokchilarga yoziladi
# ✅ Manual "📅 Yangi oy ochish" (admin bosganda) -> template tablardan yangi oy ochadi
# ✅ Xodim qo'shganda avtomatik joriy oy uchun tab yaratadi (EMPLOYEE_TEMPLATE_TAB dan duplicate)
# ✅ Jamoa ro'yxatida Tab ko'rsatadi
#
# Eslatma:
# - settings ichida quyidagilar bo'lishi kerak:
#   DEFAULT_SPREADSHEET_ID, EMPLOYEE_TEMPLATE_TAB, MONTH_TEMPLATE_TAB, GROUP_ID, ADMIN_IDS
# - sheets_service ichida:
#   duplicate_worksheet(...), create_month_and_employee_tabs(...),
#   worksheet_exists(...), get_current_month_name(), get_next_month_name()
#   (sizga bergan yangilangan sheets_service.py shu funksiyalarni berishi kerak)

import logging
from datetime import datetime

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select, update

from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.bot.states.admin_states import AddEmployeeStates, LinkSheetStates
from src.bot.keyboards.reply import get_main_menu, cancel_kb
from src.bot.filters.admin_filter import IsAnyAdminFilter
from src.services.sheets_service import sheets_service
from src.config import settings

router = Router()
router.message.filter(IsAnyAdminFilter())
router.callback_query.filter(IsAnyAdminFilter())
logger = logging.getLogger(__name__)


# =========================================================
# Helpers
# =========================================================
async def get_db_status(telegram_id: int) -> bool:
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return res.scalar_one_or_none() is not None


async def get_user_role_key(telegram_id: int) -> str:
    # Super adminlar ham admin sifatida yuradi
    if telegram_id in settings.ADMIN_IDS:
        return "admin"
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        return user.role.value if user else "admin"


# =========================================================
# 0) GLOBAL CANCEL
# =========================================================
@router.message(F.text == "🚫 Bekor qilish", StateFilter("*"))
async def cancel_global(message: types.Message, state: FSMContext):
    await state.clear()
    user_in_db = await get_db_status(message.from_user.id)
    role_key = await get_user_role_key(message.from_user.id)
    await message.answer(
        "Jarayon bekor qilindi.",
        reply_markup=get_main_menu(role_key, user_in_db=user_in_db),
    )


# =========================================================
# 1) XODIM QO'SHISH (DESIGNER YO'Q ✅)
# =========================================================
@router.message(F.text == "➕ Xodim qo'shish")
async def cmd_add_employee(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Yangi xodimning Telegram ID raqamini yuboring:", reply_markup=cancel_kb)
    await state.set_state(AddEmployeeStates.waiting_for_id)


@router.message(AddEmployeeStates.waiting_for_id)
async def process_emp_id(message: types.Message, state: FSMContext):
    if not (message.text or "").isdigit():
        return await message.answer("⚠️ ID raqam faqat raqamlardan iborat bo'lishi kerak!")

    await state.update_data(new_id=int(message.text))
    await message.answer("Xodimning Ism va Familiyasini yozing:", reply_markup=cancel_kb)
    await state.set_state(AddEmployeeStates.waiting_for_name)


@router.message(AddEmployeeStates.waiting_for_name)
async def process_emp_name(message: types.Message, state: FSMContext):
    full_name = (message.text or "").strip()
    if not full_name:
        return await message.answer("⚠️ Ism bo'sh bo'lmasin!")

    await state.update_data(full_name=full_name)

    # ✅ Designer olib tashlandi
    role_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="mobilographer"), KeyboardButton(text="copywriter")],
            [KeyboardButton(text="marketer"), KeyboardButton(text="content_maker")],
            [KeyboardButton(text="admin")],
            [KeyboardButton(text="🚫 Bekor qilish")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        f"Yaxshi, endi <b>{full_name}</b> uchun tizimdagi rolni tanlang:",
        reply_markup=role_kb,
        parse_mode="HTML",
    )
    await state.set_state(AddEmployeeStates.waiting_for_role)


@router.message(AddEmployeeStates.waiting_for_role)
async def process_emp_role(message: types.Message, state: FSMContext):
    data = await state.get_data()
    role_str = (message.text or "").strip().lower()

    if role_str == "🚫 bekor qilish":
        await state.clear()
        user_in_db = await get_db_status(message.from_user.id)
        await message.answer("Jarayon bekor qilindi.", reply_markup=get_main_menu("admin", user_in_db=user_in_db))
        return

    try:
        selected_role = UserRole[role_str]
    except KeyError:
        return await message.answer("⚠️ Iltimos, pastdagi tugmalardan birini tanlang!")

    # ✅ Joriy oy nomi (sheets_service ichida bo'lishi kerak)
    current_month = sheets_service.get_current_month_name(datetime.now())
    worksheet_name = f"{data['full_name']} {current_month}"

    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == data["new_id"]))
        user = res.scalar_one_or_none()

        # ✅ Xodim tabini avtomatik yaratish (template'dan)
        # Agar allaqachon mavjud bo'lsa create skip (idempotent)
        try:
            if not await sheets_service.worksheet_exists(settings.DEFAULT_SPREADSHEET_ID, worksheet_name):
                await sheets_service.duplicate_worksheet(
                    sheet_id=settings.DEFAULT_SPREADSHEET_ID,
                    source_worksheet=settings.EMPLOYEE_TEMPLATE_TAB,
                    new_worksheet=worksheet_name,
                )
        except Exception as e:
            logger.error(f"Employee tab create error '{worksheet_name}': {e}")

        if user:
            user.full_name = data["full_name"]
            user.role = selected_role
            user.personal_sheet_id = settings.DEFAULT_SPREADSHEET_ID
            user.worksheet_name = worksheet_name
            msg = f"🔄 <b>{data['full_name']}</b> ma'lumotlari yangilandi.\n📄 Tab: <b>{worksheet_name}</b>"
        else:
            new_user = User(
                telegram_id=data["new_id"],
                full_name=data["full_name"],
                role=selected_role,
                personal_sheet_id=settings.DEFAULT_SPREADSHEET_ID,
                worksheet_name=worksheet_name,
            )
            session.add(new_user)
            msg = (
                f"✅ Yangi xodim qo'shildi:\n"
                f"👤 <b>{data['full_name']}</b>\n"
                f"🎭 Rol: <b>{role_str}</b>\n"
                f"📄 Tab: <b>{worksheet_name}</b>"
            )

        await session.commit()

    await state.clear()
    user_in_db = await get_db_status(message.from_user.id)
    await message.answer(msg, reply_markup=get_main_menu("admin", user_in_db=user_in_db), parse_mode="HTML")


# =========================================================
# 2) TASK: ADMIN APPROVE/REJECT (saqlangan ✅)
# =========================================================
@router.callback_query(F.data.startswith("adm_app_"))
async def admin_approve_task(callback: types.CallbackQuery, bot: Bot):
    task_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!")

        task.status = "Bajarildi"

        # ✅ Ishtirokchilar: mobilographer/copywriter/marketer (designer yo'q)
        participants = [
            task.mobilographer_id,
            task.copywriter_id,
            task.marketer_id,
        ]

        success_count = 0
        for p_id in participants:
            if not p_id:
                continue

            res = await session.execute(select(User).where(User.telegram_id == p_id))
            p_user = res.scalar_one_or_none()
            if not p_user or not p_user.worksheet_name or not p_user.personal_sheet_id:
                continue

            try:
                # AH (34) ustuniga link
                await sheets_service.write_final_link(
                    p_user.personal_sheet_id,
                    p_user.worksheet_name,
                    task.row_index,
                    task.final_link or "",
                )
                await bot.send_message(
                    p_id,
                    (
                        "🎉 <b>Vazifa yakuniy tasdiqdan o'tdi!</b>\n"
                        f"📌 <b>{task.task_name}</b>\n"
                        f"🔗 {task.final_link or '—'}"
                    ),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Sheets/link write error for user_id={p_id}: {e}")

        await session.commit()

    await callback.message.edit_text(
        f"✅ Vazifa yopildi. Link {success_count} ta ishtirokchining Dashboardiga (AH) yozildi."
    )


@router.callback_query(F.data.startswith("adm_rej_"))
async def admin_reject_task(callback: types.CallbackQuery, bot: Bot):
    task_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!")

        # Marketerga qaytarish
        if task.marketer_id:
            try:
                await bot.send_message(
                    task.marketer_id,
                    (
                        "❌ <b>Vazifa rad etildi!</b>\n"
                        f"📌 <b>{task.task_name}</b>\n"
                        "Iltimos, qayta tekshirib yuboring."
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Reject notify to marketer failed: {e}")

    await callback.message.edit_text("🔴 Vazifa rad etildi va marketerga qaytarildi.")


# =========================================================
# 3) JAMOA RO'YXATI
# =========================================================
@router.message(F.text == "👥 Xodimlar")
async def cmd_list(message: types.Message):
    async with async_session() as session:
        res = await session.execute(select(User).order_by(User.role, User.full_name))
        users = res.scalars().all()

    if not users:
        return await message.answer("👥 Hozircha xodimlar yo'q.")

    lines = []
    for u in users:
        tab = u.worksheet_name if u.worksheet_name else "—"
        lines.append(f"• {u.full_name} (<code>{u.role.value}</code>) | Tab: <b>{tab}</b>")

    text = "<b>👥 Jamoa a'zolari:</b>\n\n" + "\n".join(lines)
    await message.answer(text, parse_mode="HTML")


# =========================================================
# 4) OYLIK HISOBOT
# =========================================================
@router.message(F.text == "📊 Oylik hisobot")
async def cmd_report(message: types.Message):
    link = f"https://docs.google.com/spreadsheets/d/{settings.DEFAULT_SPREADSHEET_ID}"
    await message.answer(
        f"📊 <a href='{link}'>Dashboardni ochish</a>",
        disable_web_page_preview=True,
        parse_mode="HTML",
    )


# =========================================================
# 5) MANUAL: YANGI OY OCHISH
#    - Oy template tab -> yangi oy
#    - Har xodim uchun employee template -> "FullName NewMonth"
#    - DB worksheet_name update
# =========================================================
@router.message(F.text == "📅 Yangi oy ochish")
async def cmd_open_new_month(message: types.Message):
    sheet_id = settings.DEFAULT_SPREADSHEET_ID
    now = datetime.now()
    new_month = sheets_service.get_next_month_name(now)

    # DB dan userlar
    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.full_name))).scalars().all()
        employee_names = [u.full_name for u in users if u.full_name]

    if not employee_names:
        return await message.answer("❌ Xodimlar yo'q.")

    try:
        await sheets_service.create_month_and_employee_tabs(
            sheet_id=sheet_id,
            new_month=new_month,
            employee_full_names=employee_names,
        )
    except Exception as e:
        logger.error(f"Manual month open error: {e}")
        return await message.answer("❌ Yangi oy ochishda xatolik. Template tab nomlarini tekshiring.")

    # DB update: worksheet_name = "FullName NewMonth"
    async with async_session() as session:
        users = (await session.execute(select(User))).scalars().all()
        for u in users:
            if not u.full_name:
                continue
            u.personal_sheet_id = sheet_id
            u.worksheet_name = f"{u.full_name} {new_month}"
        await session.commit()

    await message.answer(f"✅ Yangi oy ochildi: <b>{new_month}</b>\nBarcha xodimlar uchun tab yaratildi.", parse_mode="HTML")


# =========================================================
# 6) (Ixtiyoriy) Tab bog'lash (manual override)
# =========================================================
@router.message(F.text == "📅 Yangi oy ochish (manual tab)")
async def cmd_link_sheet(message: types.Message, state: FSMContext):
    """
    Agar sizga eski manual bog'lash flow ham kerak bo'lsa.
    Tugma default menu'da yo'q. Xohlasangiz reply.py ga qo'shasiz.
    """
    await state.clear()
    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.full_name))).scalars().all()

    if not users:
        return await message.answer("Xodimlar yo'q.")

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=u.full_name)] for u in users] + [[KeyboardButton(text="🚫 Bekor qilish")]],
        resize_keyboard=True,
    )
    await message.answer("Foydalanuvchini tanlang:", reply_markup=kb)
    await state.set_state(LinkSheetStates.selecting_user)


@router.message(LinkSheetStates.selecting_user)
async def process_link_user(message: types.Message, state: FSMContext):
    await state.update_data(target_name=message.text)
    await message.answer("Tab nomini yozing (masalan: 'Zilola Ixtiyorovna Mart'):", reply_markup=cancel_kb)
    await state.set_state(LinkSheetStates.waiting_for_tab_name)


@router.message(LinkSheetStates.waiting_for_tab_name)
async def process_tab_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tab_name = (message.text or "").strip()

    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.full_name == data["target_name"])
            .values(worksheet_name=tab_name, personal_sheet_id=settings.DEFAULT_SPREADSHEET_ID)
        )
        await session.commit()

    await state.clear()
    user_in_db = await get_db_status(message.from_user.id)
    await message.answer(f"✅ Tab bog'landi: <b>{tab_name}</b>", reply_markup=get_main_menu("admin", user_in_db=user_in_db), parse_mode="HTML")