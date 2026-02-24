import logging
from datetime import datetime, timedelta, date
from typing import Optional, List

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from src.database.base import async_session
from src.database.models import User, UserRole, Task
from src.services.sheets_service import sheets_service
from src.bot.states.admin_states import ContentMakerStates
from src.bot.filters.cm_or_admin_filter import IsContentMakerOrAdminFilter
from src.config import settings

logger = logging.getLogger(__name__)

router = Router()

# ✅ RBAC: Content Maker yoki Admin (Super admin ham kiradi)
router.message.filter(IsContentMakerOrAdminFilter())
router.callback_query.filter(IsContentMakerOrAdminFilter())


# ----------------------------
# Helpers
# ----------------------------

def _parse_choice_id(text: str) -> Optional[int]:
    """
    Button text: "Full Name | 123456789"
    """
    if not text or "|" not in text:
        return None
    try:
        return int(text.split("|")[-1].strip())
    except Exception:
        return None


def _today_local() -> date:
    return datetime.now().date()


def _validate_deadline_str(s: str) -> Optional[datetime]:
    """
    dd.mm.yyyy format; o'tgan sana bo'lmasin.
    """
    try:
        dt = datetime.strptime(s.strip(), "%d.%m.%Y")
    except ValueError:
        return None

    if dt.date() < _today_local():
        return None
    return dt


async def _get_user_by_telegram_id(tid: int) -> Optional[User]:
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == tid))
        return res.scalar_one_or_none()


async def _get_first_user_by_role(role: UserRole) -> Optional[User]:
    async with async_session() as session:
        res = await session.execute(select(User).where(User.role == role))
        return res.scalars().first()


async def _get_mobilographers() -> List[User]:
    async with async_session() as session:
        res = await session.execute(
            select(User).where(User.role == UserRole.mobilographer).order_by(User.full_name)
        )
        return res.scalars().all()


def _priority_keyboard() -> types.ReplyKeyboardMarkup:
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🔥 Muhim va tez")],
            [types.KeyboardButton(text="⚡️ Oddiy")],
            [types.KeyboardButton(text="☕️ Shoshilinch emas")],
            [types.KeyboardButton(text="🚫 Bekor qilish")],
        ],
        resize_keyboard=True,
    )


# ----------------------------
# Flow
# ----------------------------

@router.message(F.text == "➕ Yangi vazifa")
async def start_new_task(message: types.Message, state: FSMContext):
    await state.clear()

    mobis = await _get_mobilographers()
    if not mobis:
        return await message.answer("❌ Bazada mobilograflar yo'q. Avval admin mobilograf qo'shsin.")

    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=f"{m.full_name} | {m.telegram_id}")]
            for m in mobis
        ] + [[types.KeyboardButton(text="🚫 Bekor qilish")]],
        resize_keyboard=True,
    )

    await state.set_state(ContentMakerStates.choosing_mobilographer)
    await message.answer("📹 Mobilografni tanlang:", reply_markup=kb)


@router.message(ContentMakerStates.choosing_mobilographer)
async def process_mobi(message: types.Message, state: FSMContext):
    if (message.text or "").strip() == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Jarayon bekor qilindi.")

    mobi_tid = _parse_choice_id(message.text or "")
    if not mobi_tid:
        return await message.answer("⚠️ Iltimos, mobilografni pastdagi tugma orqali tanlang.")

    mobi = await _get_user_by_telegram_id(mobi_tid)
    if not mobi or mobi.role != UserRole.mobilographer:
        return await message.answer("⚠️ Tanlangan foydalanuvchi mobilograf emas yoki topilmadi.")

    # ✅ Tab/sheet tekshiruvi (kritik)
    if not mobi.personal_sheet_id or not mobi.worksheet_name:
        return await message.answer(
            "❌ Mobilografning Dashboard tab'i bog'lanmagan.\n"
            "Admin '📅 Yangi oy ochish' orqali ushbu mobilografga tab biriktirsin."
        )

    await state.update_data(mobi_telegram_id=mobi_tid)
    await state.set_state(ContentMakerStates.writing_task_name)
    await message.answer("📝 Vazifa nomini yozing:", reply_markup=types.ReplyKeyboardRemove())


@router.message(ContentMakerStates.writing_task_name)
async def process_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        return await message.answer("⚠️ Vazifa nomi bo'sh bo'lmasin.")

    await state.update_data(task_name=name)
    await state.set_state(ContentMakerStates.setting_deadline)
    await message.answer("📅 Deadline sanasini kiriting (kun.oy.yil, masalan: 25.02.2026):")


@router.message(ContentMakerStates.setting_deadline)
async def process_deadline(message: types.Message, state: FSMContext):
    dt = _validate_deadline_str(message.text or "")
    if not dt:
        return await message.answer("⚠️ Sana xato yoki o'tgan sana. Format: 25.02.2026")

    await state.update_data(deadline=dt)
    await state.set_state(ContentMakerStates.writing_scenario)
    await message.answer("📜 Vazifa ssenariysini yozing:")


@router.message(ContentMakerStates.writing_scenario)
async def process_scenario(message: types.Message, state: FSMContext):
    scenario = (message.text or "").strip()
    if not scenario:
        return await message.answer("⚠️ Ssenariy bo'sh bo'lmasin.")

    await state.update_data(scenario=scenario)
    await state.set_state(ContentMakerStates.choosing_priority)
    await message.answer("⭐ Muhimlik darajasini tanlang:", reply_markup=_priority_keyboard())


@router.message(ContentMakerStates.choosing_priority)
async def finalize_task(message: types.Message, state: FSMContext, bot: Bot):
    if (message.text or "").strip() == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Jarayon bekor qilindi.")

    priority = (message.text or "").strip()
    if priority not in {"🔥 Muhim va tez", "⚡️ Oddiy", "☕️ Shoshilinch emas"}:
        return await message.answer("⚠️ Iltimos, pastdagi tugmalardan tanlang.")

    data = await state.get_data()
    mobi_tid = data["mobi_telegram_id"]
    task_name = data["task_name"]
    scenario = data["scenario"]
    deadline: datetime = data["deadline"]

    mobi = await _get_user_by_telegram_id(mobi_tid)
    if not mobi:
        await state.clear()
        return await message.answer("❌ Mobilograf topilmadi. Qaytadan urinib ko'ring.")

    copy = await _get_first_user_by_role(UserRole.copywriter)
    market = await _get_first_user_by_role(UserRole.marketer)

    # 1) Avval Sheetsga yozamiz
    try:
        row_idx = await sheets_service.add_task_to_sheet(
            mobi.personal_sheet_id,
            mobi.worksheet_name,
            task_name,
            deadline.strftime("%d.%m.%Y"),
            priority,
        )
    except Exception as e:
        logger.error(f"Sheets add_task_to_sheet error: {e}")
        await state.clear()
        return await message.answer(
            "❌ Google Sheets'ga yozishda xatolik.\n"
            "Tab nomi va sheet_id to'g'riligini tekshiring yoki keyinroq urinib ko'ring."
        )

    # 2) DB task yaratamiz
    async with async_session() as session:
        new_task = Task(
            task_name=task_name,
            scenario=scenario,
            deadline=deadline,
            priority=priority,
            status="Yangi",
            content_maker_id=message.from_user.id,
            mobilographer_id=mobi.telegram_id,
            copywriter_id=copy.telegram_id if copy else None,
            marketer_id=market.telegram_id if market else None,
            designer_id=None,
            row_index=row_idx,
            final_link=None,
        )
        session.add(new_task)
        await session.commit()
        await session.refresh(new_task)

    # ✅ 3) Guruhga xabar (siz so'ragansiz)
    try:
        await bot.send_message(
            settings.GROUP_ID,
            (
                "🆕 <b>Yangi vazifa berildi!</b>\n"
                f"📌 <b>{task_name}</b>\n"
                f"👤 Mobilograf: <b>{mobi.full_name}</b>\n"
                f"📅 Yakuniy deadline: <b>{deadline.strftime('%d.%m.%Y')}</b>\n"
                "🔔 Iltimos, vazifalar ro'yxatini tekshiring."
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Group notify failed: {e}")

    # 4) Notificationlar
    warnings = []

    mobi_deadline = (deadline - timedelta(days=3)).strftime("%d.%m.%Y")
    await bot.send_message(
        mobi.telegram_id,
        (
            "📹 <b>Yangi vazifa (Mobilograf)!</b>\n"
            f"📌 <b>{task_name}</b>\n"
            f"📅 Deadline: <b>{mobi_deadline}</b>\n"
            f"⭐ Prioritet: <b>{priority}</b>\n\n"
            f"📜 <b>Ssenariy:</b>\n{scenario}"
        ),
        parse_mode="HTML",
    )

    if copy:
        copy_deadline = (deadline - timedelta(days=1)).strftime("%d.%m.%Y")
        try:
            await bot.send_message(
                copy.telegram_id,
                (
                    "✍️ <b>Yangi vazifa (Copywriter)!</b>\n"
                    f"📌 <b>{task_name}</b>\n"
                    f"📅 Deadline: <b>{copy_deadline}</b>\n"
                    f"⭐ Prioritet: <b>{priority}</b>\n\n"
                    f"📜 <b>Ssenariy:</b>\n{scenario}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Copywriter notify failed: {e}")
    else:
        warnings.append("⚠️ Copywriter topilmadi (bazada yo'q).")

    if market:
        try:
            await bot.send_message(
                market.telegram_id,
                (
                    "🚀 <b>Yangi vazifa (Marketer)!</b>\n"
                    f"📌 <b>{task_name}</b>\n"
                    f"📅 Deadline: <b>{deadline.strftime('%d.%m.%Y')}</b>\n"
                    f"⭐ Prioritet: <b>{priority}</b>\n\n"
                    "✅ Post tayyor bo'lgach, '🚀 Postni nashr etish' orqali link yuboring."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Marketer notify failed: {e}")
    else:
        warnings.append("⚠️ Marketer topilmadi (bazada yo'q).")

    await state.clear()

    resp = (
        "✅ Vazifa yaratildi!\n"
        f"📌 {task_name}\n"
        f"📍 Sheets row: {row_idx}\n"
    )
    if warnings:
        resp += "\n" + "\n".join(warnings)

    await message.answer(resp)