# src/bot/handlers/employee.py

import logging
from typing import List, Optional, Tuple

from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.services.sheets_service import sheets_service
from src.config import settings

router = Router()
logger = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================

def _role_task_filter(role: UserRole, telegram_id: int):
    """
    Task modelida 'user_id' yo'q. Shuning uchun ro'lga qarab mos *_id field bo'yicha filter qilamiz.
    """
    if role == UserRole.mobilographer:
        return Task.mobilographer_id == telegram_id
    if role == UserRole.copywriter:
        return Task.copywriter_id == telegram_id
    if role == UserRole.designer:
        return Task.designer_id == telegram_id
    if role == UserRole.marketer:
        return Task.marketer_id == telegram_id
    return None


async def _get_user_and_role(telegram_id: int) -> Tuple[Optional[User], Optional[UserRole]]:
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        if not user:
            return None, None
        return user, user.role


async def _get_active_tasks_for_user(session, user: User) -> List[Task]:
    cond = _role_task_filter(user.role, user.telegram_id)
    if cond is None:
        return []
    res = await session.execute(
        select(Task)
        .where(cond, Task.status != "Bajarildi")
        .order_by(Task.deadline.asc())
    )
    return res.scalars().all()


async def _safe_update_sheet_progress(
    user: User,
    task: Task,
    holati_text: str,
    status_text: Optional[str] = None,
) -> None:
    """
    Sheets update xatolari bot oqimini yiqitmasin.
    Faqat mavjud servis metodlaridan foydalanamiz: update_progress_status (M=13, AC=29).
    """
    if not user.personal_sheet_id or not user.worksheet_name:
        logger.warning(
            f"Sheets update skipped: user '{user.full_name}' has no sheet_id/tab. "
            f"(sheet_id={user.personal_sheet_id}, tab={user.worksheet_name})"
        )
        return

    if not task.row_index or task.row_index <= 0:
        logger.warning(f"Sheets update skipped: invalid row_index for task_id={task.id}: {task.row_index}")
        return

    try:
        await sheets_service.update_progress_status(
            user.personal_sheet_id,
            user.worksheet_name,
            task.row_index,
            holati_text=holati_text,
            status_text=status_text,
        )
    except Exception as e:
        logger.error(f"Sheets update_progress_status error (task_id={task.id}, user={user.full_name}): {e}")


async def _notify_admins_for_review(bot: Bot, task: Task, performer: User) -> None:
    """
    Xodim 'Bajarildi' qilganda adminga tekshiruv uchun yuboradi.
    Admin tarafdagi callbacklar admin.py da mavjud: adm_app_{task_id}, adm_rej_{task_id}
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"adm_app_{task.id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_rej_{task.id}"),
        ]
    ])

    text = (
        "🔎 <b>Tekshiruvga yuborildi!</b>\n"
        f"👤 Ijrochi: <b>{performer.full_name}</b> (<code>{performer.role.value}</code>)\n"
        f"📌 Vazifa: <b>{task.task_name}</b>\n"
        f"⏳ Holat (DB): <b>{task.status}</b>\n"
    )
    if task.final_link:
        text += f"🔗 Link: {task.final_link}\n"

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify admin_id={admin_id}: {e}")


def _status_map(state_val: str) -> Tuple[str, str, Optional[str]]:
    """
    Callback state_val -> (db_status, holati_text(M), status_text(AC))
    """
    if state_val == "jarayon":
        return "Jarayonda", "Jarayonda", "Jarayonda 🟡"
    if state_val == "resurs":
        return "Resurs yo'qligi", "Resurs yo'qligi", "To'xtadi 🔴"
    if state_val == "bajarildi":
        # DB’da yakuniy "Bajarildi"ni admin tasdiqlaydi; xodim bajarib bo'lganda "Tekshirilmoqda"ga yuboramiz.
        return "Tekshirilmoqda", "Bajarildi", "Tekshirilmoqda 🔵"
    # fallback
    return "Jarayonda", "Jarayonda", "Jarayonda 🟡"


# ============================================================
# Handlers
# ============================================================

@router.message(F.text == "📝 Mening vazifalarim")
async def cmd_my_tasks(message: types.Message):
    user, role = await _get_user_and_role(message.from_user.id)
    if not user:
        return await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")

    if role not in {UserRole.mobilographer, UserRole.copywriter, UserRole.designer, UserRole.marketer}:
        return await message.answer("ℹ️ Bu bo'lim faqat ijrochilar uchun (mobilographer/copywriter/designer/marketer).")

    async with async_session() as session:
        tasks = await _get_active_tasks_for_user(session, user)

    if not tasks:
        return await message.answer("✅ Sizda hozircha faol vazifalar yo'q.")

    lines = []
    for i, t in enumerate(tasks, 1):
        dl = t.deadline.strftime("%d.%m.%Y") if t.deadline else "—"
        lines.append(f"{i}. <b>{t.task_name}</b>\n   📅 Deadline: <b>{dl}</b>\n   📍 Holat: <b>{t.status}</b>")

    await message.answer("📝 <b>Sizning vazifalaringiz:</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")


@router.message(F.text == "✅ Statusni yangilash")
async def cmd_update_status(message: types.Message):
    user, role = await _get_user_and_role(message.from_user.id)
    if not user:
        return await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")

    if role not in {UserRole.mobilographer, UserRole.copywriter, UserRole.designer, UserRole.marketer}:
        return await message.answer("ℹ️ Bu bo'lim faqat ijrochilar uchun (mobilographer/copywriter/designer/marketer).")

    async with async_session() as session:
        tasks = await _get_active_tasks_for_user(session, user)

    if not tasks:
        return await message.answer("✅ Sizda hozircha faol vazifalar yo'q.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📌 {t.task_name[:35]}", callback_data=f"select_task_status_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifaning holatini o'zgartirmoqchisiz?", reply_markup=kb)


@router.callback_query(F.data.startswith("select_task_status_"))
async def process_task_selection(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[3])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)

        # Egasi/ijrochisi shu usermi? (role-based check)
        res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            return await callback.answer("Siz ro'yxatdan o'tmagansiz.", show_alert=True)

        cond = _role_task_filter(user.role, user.telegram_id)
        if cond is None:
            return await callback.answer("Siz ijrochi rolida emassiz.", show_alert=True)

        # Task shu userga tegishliligini tekshirish:
        allowed = False
        if user.role == UserRole.mobilographer and task.mobilographer_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.copywriter and task.copywriter_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.designer and task.designer_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.marketer and task.marketer_id == user.telegram_id:
            allowed = True

        if not allowed:
            return await callback.answer("Bu vazifa sizga biriktirilmagan.", show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Jarayonda", callback_data=f"set_prog_jarayon_{task_id}")],
        [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"set_prog_bajarildi_{task_id}")],
        [InlineKeyboardButton(text="❌ Resurs yo'qligi", callback_data=f"set_prog_resurs_{task_id}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_tasks")],
    ])

    await callback.message.edit_text(
        f"📌 <b>Vazifa:</b> {task.task_name}\n\nUshbu vazifa uchun yangi holatni tanlang:",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_prog_"))
async def process_status_change(callback: types.CallbackQuery, bot: Bot):
    # format: set_prog_<state>_<task_id>
    _, _, state_val, task_id_str = callback.data.split("_")
    task_id = int(task_id_str)

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)

        res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            return await callback.answer("Siz ro'yxatdan o'tmagansiz.", show_alert=True)

        # Task ownership check
        allowed = False
        if user.role == UserRole.mobilographer and task.mobilographer_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.copywriter and task.copywriter_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.designer and task.designer_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.marketer and task.marketer_id == user.telegram_id:
            allowed = True

        if not allowed:
            return await callback.answer("Bu vazifa sizga biriktirilmagan.", show_alert=True)

        db_status, holati_text, status_text = _status_map(state_val)

        # DB status
        task.status = db_status
        await session.commit()

    # Sheets update (best-effort)
    await _safe_update_sheet_progress(user, task, holati_text=holati_text, status_text=status_text)

    # Admin review notify when "bajarildi"
    if state_val == "bajarildi":
        await _notify_admins_for_review(bot, task, user)
        await callback.message.edit_text("✅ Vazifa yakunlandi va tekshiruvga yuborildi.")
    else:
        await callback.message.edit_text(
            f"✅ Vazifa holati '<b>{db_status}</b>'ga o'zgartirildi.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: types.CallbackQuery):
    """
    Inline UI'ni tozalab, qayta ro'yxat chiqaramiz.
    """
    try:
        await callback.message.delete()
    except Exception:
        pass
    # callback.message bu Message; aiogram3 da handlerni bevosita chaqirish mumkin
    await cmd_update_status(callback.message)


# Ixtiyoriy: Agar boshqa joylarda ishlatilsa
@router.callback_query(F.data.startswith("accept_task_"))
async def accept_task(callback: types.CallbackQuery):
    """
    Vazifani "Ishni boshlamoqchiman" deb belgilash (ixtiyoriy).
    Buni hozirgi loyihada default UI ishlatmayapti, lekin oldingi kodda bor edi.
    """
    task_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)

        res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            return await callback.answer("Siz ro'yxatdan o'tmagansiz.", show_alert=True)

        # Ownership check
        allowed = False
        if user.role == UserRole.mobilographer and task.mobilographer_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.copywriter and task.copywriter_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.designer and task.designer_id == user.telegram_id:
            allowed = True
        elif user.role == UserRole.marketer and task.marketer_id == user.telegram_id:
            allowed = True

        if not allowed:
            return await callback.answer("Bu vazifa sizga biriktirilmagan.", show_alert=True)

        task.status = "Ishni boshlamoqchiman"
        await session.commit()

    await _safe_update_sheet_progress(user, task, holati_text="Ishni boshlamoqchiman", status_text="Jarayonda 🟡")
    await callback.message.edit_text("✅ Vazifani qabul qildingiz. Ishga omad!")