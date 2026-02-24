# src/bot/handlers/admin.py

import logging
from typing import Optional, Tuple

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select, update

from src.config import settings
from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.bot.states.admin_states import AddEmployeeStates, LinkSheetStates
from src.bot.keyboards.reply import get_main_menu, cancel_kb
from src.bot.filters.admin_filter import IsAnyAdminFilter
from src.services.sheets_service import sheets_service

router = Router()
router.message.filter(IsAnyAdminFilter())
logger = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================

async def get_db_user(telegram_id: int) -> Optional[User]:
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return res.scalar_one_or_none()


async def get_db_status(telegram_id: int) -> bool:
    return (await get_db_user(telegram_id)) is not None


def _is_super_admin(telegram_id: int) -> bool:
    return telegram_id in settings.ADMIN_IDS


def _admin_main_menu(message_from_user_id: int, user_in_db: bool) -> ReplyKeyboardMarkup:
    # Super admin ham, db-admin ham admin menuni ko'radi
    return get_main_menu("admin", user_in_db=user_in_db)


def _employee_role_keyboard(is_super_admin: bool) -> ReplyKeyboardMarkup:
    """
    Admin rolini faqat super admin bera olsin (privilege escalation oldini olish).
    """
    rows = [
        [KeyboardButton(text="mobilographer"), KeyboardButton(text="copywriter")],
        [KeyboardButton(text="marketer"), KeyboardButton(text="designer")],
        [KeyboardButton(text="content_maker")],
    ]
    if is_super_admin:
        rows.append([KeyboardButton(text="admin")])
    rows.append([KeyboardButton(text="🚫 Bekor qilish")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _parse_user_choice(text: str) -> Optional[int]:
    """
    LinkSheetStates user tanlash uchun button text format:
      "Full Name | 123456789"
    Shu yerdan telegram_id ni ajratib olamiz.
    """
    if not text:
        return None
    if "|" not in text:
        return None
    try:
        tid = int(text.split("|")[-1].strip())
        return tid
    except Exception:
        return None


async def _get_user_label(session, u: User) -> str:
    # UI uchun user label
    return f"{u.full_name} | {u.telegram_id}"


# ============================================================
# 0. GLOBAL CANCEL
# ============================================================

@router.message(F.text == "🚫 Bekor qilish", StateFilter("*"))
async def cancel_global(message: types.Message, state: FSMContext):
    await state.clear()
    user_in_db = await get_db_status(message.from_user.id)
    await message.answer(
        "Jarayon bekor qilindi.",
        reply_markup=_admin_main_menu(message.from_user.id, user_in_db=user_in_db),
    )


# ============================================================
# 1. XODIM QO'SHISH
# ============================================================

@router.message(F.text == "➕ Xodim qo'shish")
async def cmd_add_employee(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Yangi xodimning Telegram ID raqamini yuboring:",
        reply_markup=cancel_kb,
    )
    await state.set_state(AddEmployeeStates.waiting_for_id)


@router.message(AddEmployeeStates.waiting_for_id)
async def process_emp_id(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        return await message.answer("⚠️ ID raqam faqat raqamlardan iborat bo'lishi kerak!")

    await state.update_data(new_id=int(message.text))
    await message.answer("Xodimning Ism va Familiyasini yozing:", reply_markup=cancel_kb)
    await state.set_state(AddEmployeeStates.waiting_for_name)


@router.message(AddEmployeeStates.waiting_for_name)
async def process_emp_name(message: types.Message, state: FSMContext):
    full_name = (message.text or "").strip()
    if not full_name:
        return await message.answer("⚠️ Ism-familiya bo'sh bo'lmasin.")

    await state.update_data(full_name=full_name)

    role_kb = _employee_role_keyboard(is_super_admin=_is_super_admin(message.from_user.id))
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

    # Admin rolini faqat super admin bera oladi
    if role_str == "admin" and not _is_super_admin(message.from_user.id):
        return await message.answer("⛔ Admin rolini faqat Super Admin bera oladi.")

    try:
        selected_role = UserRole[role_str]
    except KeyError:
        return await message.answer("⚠️ Iltimos, pastdagi tugmalardan birini tanlang!")

    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == data["new_id"]))
        user = res.scalar_one_or_none()

        if user:
            user.full_name = data["full_name"]
            user.role = selected_role
            msg = f"🔄 <b>{data['full_name']}</b> ma'lumotlari yangilandi.\n🎭 Rol: <b>{selected_role.value}</b>"
        else:
            new_user = User(
                telegram_id=data["new_id"],
                full_name=data["full_name"],
                role=selected_role,
                personal_sheet_id=settings.DEFAULT_SPREADSHEET_ID,
                worksheet_name=None,
            )
            session.add(new_user)
            msg = (
                "✅ Yangi xodim qo'shildi:\n"
                f"👤 <b>{data['full_name']}</b>\n"
                f"🎭 Rol: <b>{selected_role.value}</b>\n"
                f"📊 Sheet: <code>{settings.DEFAULT_SPREADSHEET_ID}</code>"
            )

        await session.commit()

    await state.clear()
    user_in_db = await get_db_status(message.from_user.id)
    await message.answer(msg, reply_markup=_admin_main_menu(message.from_user.id, user_in_db=user_in_db), parse_mode="HTML")


# ============================================================
# 2. ADMIN TASDIQLASH / RAD ETISH
# ============================================================

@router.callback_query(F.data.startswith("adm_app_"))
async def admin_approve_task(callback: types.CallbackQuery, bot: Bot):
    """
    Marketer link yuborganidan keyin admin tasdiqlaydi.
    Tasdiqlansa:
      - task.status = "Bajarildi"
      - task.final_link AH(34) ga ishtirokchilar tabiga yoziladi (worksheet_name bo'lsa)
    """
    try:
        task_id = int(callback.data.split("_")[2])
    except Exception:
        return await callback.answer("Callback format xato!", show_alert=True)

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)

        if not task.final_link:
            return await callback.answer("Bu vazifada link yo'q. Avval marketer link yuborsin.", show_alert=True)

        # Yakuniy yopish
        task.status = "Bajarildi"

        participants = [
            task.mobilographer_id,
            task.copywriter_id,
            task.designer_id,
            task.marketer_id,
        ]

        success_count = 0
        fail_count = 0

        for p_tid in participants:
            if not p_tid:
                continue

            res = await session.execute(select(User).where(User.telegram_id == p_tid))
            p_user = res.scalar_one_or_none()
            if not p_user or not p_user.personal_sheet_id or not p_user.worksheet_name:
                fail_count += 1
                continue

            try:
                await sheets_service.write_final_link(
                    p_user.personal_sheet_id,
                    p_user.worksheet_name,
                    task.row_index,
                    task.final_link,
                )
                # xodimga xabar
                try:
                    await bot.send_message(
                        p_tid,
                        f"🎉 Vazifa yakuniy tasdiqdan o'tdi!\n📌 <b>{task.task_name}</b>\n🔗 {task.final_link}",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

                success_count += 1
            except Exception as e:
                logger.error(f"Sheets write_final_link error: task_id={task.id}, user={getattr(p_user,'full_name',p_tid)}: {e}")
                fail_count += 1

        await session.commit()

    await callback.message.edit_text(
        f"✅ Vazifa yopildi.\n"
        f"🔗 Link {success_count} ta dashboardga (AH) yozildi.\n"
        f"⚠️ {fail_count} ta holatda esa xodim tab/sheet bog'lanmagan yoki xatolik bo'ldi."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_rej_"))
async def admin_reject_task(callback: types.CallbackQuery, bot: Bot):
    try:
        task_id = int(callback.data.split("_")[2])
    except Exception:
        return await callback.answer("Callback format xato!", show_alert=True)

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)

        # Rad etilganda DB status (ixtiyoriy): "Rad etildi"
        task.status = "Rad etildi"

        if task.marketer_id:
            try:
                await bot.send_message(
                    task.marketer_id,
                    f"❌ <b>Vazifa rad etildi!</b>\n📌 <b>{task.task_name}</b>\nIltimos, tekshirib qayta yuboring.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Reject notify failed to marketer_id={task.marketer_id}: {e}")

        await session.commit()

    await callback.message.edit_text("🔴 Vazifa rad etildi va marketerga qaytarildi.")
    await callback.answer()


# ============================================================
# 3. JAMOANI KO'RISH
# ============================================================

@router.message(F.text == "👥 Xodimlar")
async def cmd_list(message: types.Message):
    async with async_session() as session:
        res = await session.execute(select(User).order_by(User.role))
        users = res.scalars().all()

    if not users:
        return await message.answer("👥 Hozircha xodimlar yo'q.")

    text = "<b>👥 Jamoa a'zolari:</b>\n\n"
    for u in users:
        tab = u.worksheet_name if u.worksheet_name else "—"
        text += f"• {u.full_name} (<code>{u.role.value}</code>) | Tab: <code>{tab}</code>\n"

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📊 Oylik hisobot")
async def cmd_report(message: types.Message):
    link = f"https://docs.google.com/spreadsheets/d/{settings.DEFAULT_SPREADSHEET_ID}"
    await message.answer(
        f"📊 <a href='{link}'>Dashboardni ochish</a>",
        disable_web_page_preview=True,
        parse_mode="HTML",
    )


# ============================================================
# 4. YANGI OY OCHISH (TAB BOG'LASH)
# ============================================================

@router.message(F.text == "📅 Yangi oy ochish")
async def cmd_link_sheet(message: types.Message, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        res = await session.execute(select(User).order_by(User.role))
        users = res.scalars().all()

    if not users:
        return await message.answer("Xodimlar yo'q.")

    # Full name collision bo'lmasligi uchun telegram_id bilan chiqaramiz
    kb_rows = []
    async with async_session() as session:
        for u in users:
            kb_rows.append([KeyboardButton(text=await _get_user_label(session, u))])
    kb_rows.append([KeyboardButton(text="🚫 Bekor qilish")])

    kb = ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True)
    await message.answer("Foydalanuvchini tanlang:", reply_markup=kb)
    await state.set_state(LinkSheetStates.selecting_user)


@router.message(LinkSheetStates.selecting_user)
async def process_link_user(message: types.Message, state: FSMContext):
    tid = _parse_user_choice(message.text or "")
    if not tid:
        return await message.answer("⚠️ Iltimos, pastdagi tugmalardan foydalanuvchini tanlang.")

    await state.update_data(target_telegram_id=tid)
    await message.answer("Tab nomini yozing (masalan: Yanvar):", reply_markup=cancel_kb)
    await state.set_state(LinkSheetStates.waiting_for_tab_name)


@router.message(LinkSheetStates.waiting_for_tab_name)
async def process_tab_name(message: types.Message, state: FSMContext):
    tab_name = (message.text or "").strip()
    if not tab_name:
        return await message.answer("⚠️ Tab nomi bo'sh bo'lmasin.")

    data = await state.get_data()
    target_tid = data.get("target_telegram_id")
    if not target_tid:
        await state.clear()
        user_in_db = await get_db_status(message.from_user.id)
        return await message.answer("⚠️ Ichki xatolik: target user topilmadi.", reply_markup=_admin_main_menu(message.from_user.id, user_in_db=user_in_db))

    async with async_session() as session:
        await session.execute(
            update(User).where(User.telegram_id == target_tid).values(worksheet_name=tab_name)
        )
        await session.commit()

    await state.clear()
    user_in_db = await get_db_status(message.from_user.id)
    await message.answer(
        f"✅ Tab bog'landi: <b>{tab_name}</b>",
        reply_markup=_admin_main_menu(message.from_user.id, user_in_db=user_in_db),
        parse_mode="HTML",
    )