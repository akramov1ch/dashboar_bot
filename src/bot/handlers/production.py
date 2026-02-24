# src/bot/handlers/production.py

import logging
from datetime import datetime
from typing import List, Optional

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy import select

from src.config import settings
from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.services.sheets_service import sheets_service
from src.bot.states.admin_states import ProductionStates
from src.bot.filters.role_filter import RoleFilter

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Routers (RBAC)
# ------------------------------------------------------------
router = Router()

router_mobi = Router()
router_copy = Router()
router_des = Router()
router_mkt = Router()

router_mobi.message.filter(RoleFilter(UserRole.mobilographer))
router_copy.message.filter(RoleFilter(UserRole.copywriter))
router_des.message.filter(RoleFilter(UserRole.designer))
router_mkt.message.filter(RoleFilter(UserRole.marketer))

router_mobi.callback_query.filter(RoleFilter(UserRole.mobilographer))
router_copy.callback_query.filter(RoleFilter(UserRole.copywriter))
router_des.callback_query.filter(RoleFilter(UserRole.designer))
router_mkt.callback_query.filter(RoleFilter(UserRole.marketer))

# Barcha role-routerlarni asosiy routerga ulaymiz (main.py include_routers ichida production.router yetarli bo'ladi)
router.include_router(router_mobi)
router.include_router(router_copy)
router.include_router(router_des)
router.include_router(router_mkt)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
async def _get_user_by_tid(session, telegram_id: int) -> Optional[User]:
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return res.scalar_one_or_none()


def _task_owner_ok(task: Task, role: UserRole, telegram_id: int) -> bool:
    if role == UserRole.mobilographer:
        return task.mobilographer_id == telegram_id
    if role == UserRole.copywriter:
        return task.copywriter_id == telegram_id
    if role == UserRole.designer:
        return task.designer_id == telegram_id
    if role == UserRole.marketer:
        return task.marketer_id == telegram_id
    return False


async def _get_active_tasks(telegram_id: int, role: UserRole) -> List[Task]:
    async with async_session() as session:
        if role == UserRole.mobilographer:
            res = await session.execute(select(Task).where(Task.mobilographer_id == telegram_id, Task.status != "Bajarildi"))
        elif role == UserRole.copywriter:
            res = await session.execute(select(Task).where(Task.copywriter_id == telegram_id, Task.status != "Bajarildi"))
        elif role == UserRole.designer:
            res = await session.execute(select(Task).where(Task.designer_id == telegram_id, Task.status != "Bajarildi"))
        elif role == UserRole.marketer:
            res = await session.execute(select(Task).where(Task.marketer_id == telegram_id, Task.status != "Bajarildi"))
        else:
            return []
        return res.scalars().all()


async def _safe_sheet_progress(user: User, task: Task, holati_text: str, status_text: Optional[str] = None) -> None:
    """
    Sheets update best-effort:
    - user.personal_sheet_id + user.worksheet_name bo'lmasa skip
    - row_index invalid bo'lsa skip
    """
    if not user.personal_sheet_id or not user.worksheet_name:
        logger.warning(f"Sheets skip: user has no sheet/tab: {user.full_name} ({user.telegram_id})")
        return
    if not task.row_index or task.row_index <= 0:
        logger.warning(f"Sheets skip: invalid row_index task_id={task.id}: {task.row_index}")
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
        logger.error(f"Sheets update_progress_status error task_id={task.id}: {e}")


def _fmt_deadline(task: Task) -> str:
    try:
        return task.deadline.strftime("%d.%m.%Y")
    except Exception:
        return "—"


def _admin_approval_keyboard(task_id: int) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"adm_app_{task_id}"),
            types.InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_rej_{task_id}")
        ]
    ])


# ------------------------------------------------------------
# Global cancel (production states)
# ------------------------------------------------------------
@router.message(F.text == "🚫 Bekor qilish", StateFilter("*"))
async def cancel_any_state(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Jarayon bekor qilindi.", reply_markup=types.ReplyKeyboardRemove())


# ============================================================
# 1) MOBILOGRAPHER: MUHOKAMA UCHUN GURUHGA YUBORISH
# ============================================================

@router_mobi.message(F.text == "📤 Tekshirishga yuborish")
async def mobi_review_start(message: types.Message):
    tasks = await _get_active_tasks(message.from_user.id, UserRole.mobilographer)
    if not tasks:
        return await message.answer("Sizda faol vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name[:60], callback_data=f"rev_m_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifani muhokama guruhiga yubormoqchisiz?", reply_markup=kb)


@router_mobi.callback_query(F.data.startswith("rev_m_"))
async def mobi_review_media(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])

    # ownership check
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)
        if not _task_owner_ok(task, UserRole.mobilographer, callback.from_user.id):
            return await callback.answer("Bu vazifa sizga tegishli emas!", show_alert=True)

    await state.update_data(task_id=task_id)
    await state.set_state(ProductionStates.waiting_for_review_media)
    await callback.message.answer("Vazifa mediasini (video/rasm) yuboring:")


@router_mobi.message(ProductionStates.waiting_for_review_media)
async def mobi_review_to_group(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return await message.answer("Ichki xatolik: task tanlanmagan. Qaytadan urinib ko'ring.")

    group_id = settings.GROUP_ID

    async with async_session() as session:
        task = await session.get(Task, task_id)
        user = await _get_user_by_tid(session, message.from_user.id)

    if not task or not user:
        await state.clear()
        return await message.answer("Vazifa yoki foydalanuvchi topilmadi.")

    # Groupga audit xabari
    header = (
        "🎬 <b>Muhokama uchun media</b>\n"
        f"🆔 Task ID: <code>{task.id}</code>\n"
        f"📌 Vazifa: <b>{task.task_name}</b>\n"
        f"📅 Deadline: <b>{_fmt_deadline(task)}</b>\n"
        f"👤 Kimdan: <b>{user.full_name}</b>\n"
    )
    try:
        await bot.send_message(group_id, header, parse_mode="HTML")
        await message.copy_to(group_id)
    except Exception as e:
        logger.error(f"Failed to send review media to group: {e}")
        await state.clear()
        return await message.answer("❌ Guruhga yuborishda xatolik. Admin bilan tekshiring.")

    await state.clear()
    await message.answer("✅ Media guruhga yuborildi.")


# ============================================================
# 2) MOBILOGRAPHER: BAJARILDI (VIDEO + COVER)
# ============================================================

@router_mobi.message(F.text == "✅ Bajarildi")
async def mobi_done_start(message: types.Message):
    tasks = await _get_active_tasks(message.from_user.id, UserRole.mobilographer)
    if not tasks:
        return await message.answer("Sizda faol vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name[:60], callback_data=f"done_m_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifani yakunlamoqchisiz?", reply_markup=kb)


@router_mobi.callback_query(F.data.startswith("done_m_"))
async def mobi_done_video_prompt(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)
        if not _task_owner_ok(task, UserRole.mobilographer, callback.from_user.id):
            return await callback.answer("Bu vazifa sizga tegishli emas!", show_alert=True)

    await state.update_data(task_id=task_id)
    await state.set_state(ProductionStates.waiting_for_video_file)
    await callback.message.answer("Sifatni saqlash uchun <b>Video faylni</b> (Document ko'rinishida) yuboring:", parse_mode="HTML")


@router_mobi.message(ProductionStates.waiting_for_video_file, F.document)
async def mobi_done_cover_prompt(message: types.Message, state: FSMContext):
    await state.update_data(video_file_id=message.document.file_id)
    await state.set_state(ProductionStates.waiting_for_cover_file)
    await message.answer("Endi <b>Cover rasmini</b> fayl formatida (Document) yuboring:", parse_mode="HTML")


@router_mobi.message(ProductionStates.waiting_for_video_file)
async def mobi_done_video_wrong_format(message: types.Message):
    await message.answer("⚠️ Iltimos, videoni <b>Document</b> ko'rinishida yuboring (siqilmasin).", parse_mode="HTML")


@router_mobi.message(ProductionStates.waiting_for_cover_file, F.document)
async def mobi_done_final(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return await message.answer("Ichki xatolik: task yo'q. Qaytadan urinib ko'ring.")

    now = datetime.now()

    async with async_session() as session:
        task = await session.get(Task, task_id)
        user = await _get_user_by_tid(session, message.from_user.id)
        if not task or not user:
            await state.clear()
            return await message.answer("Vazifa yoki foydalanuvchi topilmadi.")

        if not _task_owner_ok(task, UserRole.mobilographer, user.telegram_id):
            await state.clear()
            return await message.answer("⛔ Bu vazifa sizga tegishli emas.")

        # Dizaynerni topish
        designer = (await session.execute(select(User).where(User.role == UserRole.designer))).scalars().first()

        task.mobi_done_at = now
        task.status = "Tekshirilmoqda"
        # cover file_id ni DBga saqlash yo'q (modelda field yo'q), shuning uchun faqat flow uchun foydalanamiz

        await session.commit()

    # Sheets: M va AC
    await _safe_sheet_progress(
        user,
        task,
        holati_text=f"Bajarildi {now.strftime('%d.%m %H:%M')}",
        status_text="Tekshirilmoqda 🔵",
    )

    # Dizaynerga cover topshirish trigger
    if designer:
        try:
            caption = (
                "🎨 <b>Yangi cover vazifasi!</b>\n"
                f"📌 Vazifa: <b>{task.task_name}</b>\n"
                f"📅 Deadline: <b>{_fmt_deadline(task)}</b>\n\n"
                "Mobilograf cover uchun rasmni yukladi. Iltimos, cover tayyorlab topshiring."
            )
            await bot.send_document(designer.telegram_id, message.document.file_id, caption=caption, parse_mode="HTML")
            # DB'da designer biriktirish
            async with async_session() as session2:
                task2 = await session2.get(Task, task.id)
                if task2:
                    task2.designer_id = designer.telegram_id
                    await session2.commit()
        except Exception as e:
            logger.error(f"Failed to notify designer: {e}")

    await state.clear()
    await message.answer("✅ Video va Cover qabul qilindi. Dizaynerga xabar yuborildi.")


@router_mobi.message(ProductionStates.waiting_for_cover_file)
async def mobi_done_cover_wrong_format(message: types.Message):
    await message.answer("⚠️ Iltimos, cover rasmini ham <b>Document</b> ko'rinishida yuboring.", parse_mode="HTML")


# ============================================================
# 3) DESIGNER: COVERNI TOPSHIRISH
# ============================================================

@router_des.message(F.text == "🎨 Coverni topshirish")
async def design_done_start(message: types.Message):
    tasks = await _get_active_tasks(message.from_user.id, UserRole.designer)
    if not tasks:
        return await message.answer("Sizga biriktirilgan cover vazifasi yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name[:60], callback_data=f"done_d_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifa uchun coverni topshirasiz?", reply_markup=kb)


@router_des.callback_query(F.data.startswith("done_d_"))
async def design_done_file_prompt(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)
        if not _task_owner_ok(task, UserRole.designer, callback.from_user.id):
            return await callback.answer("Bu vazifa sizga tegishli emas!", show_alert=True)

    await state.update_data(task_id=task_id)
    await state.set_state(ProductionStates.waiting_for_design_file)
    await callback.message.answer("Tayyor coverni <b>fayl formatida</b> (Document) yuboring:", parse_mode="HTML")


@router_des.message(ProductionStates.waiting_for_design_file, F.document)
async def design_done_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return await message.answer("Ichki xatolik: task yo'q.")

    now = datetime.now()
    async with async_session() as session:
        task = await session.get(Task, task_id)
        user = await _get_user_by_tid(session, message.from_user.id)
        if not task or not user:
            await state.clear()
            return await message.answer("Vazifa yoki foydalanuvchi topilmadi.")
        if not _task_owner_ok(task, UserRole.designer, user.telegram_id):
            await state.clear()
            return await message.answer("⛔ Bu vazifa sizga tegishli emas.")

        task.design_done_at = now
        await session.commit()

    # Sheets update (best-effort)
    await _safe_sheet_progress(user, task, holati_text=f"Cover topshirildi {now.strftime('%d.%m %H:%M')}")
    await state.clear()
    await message.answer("✅ Cover qabul qilindi.")


@router_des.message(ProductionStates.waiting_for_design_file)
async def design_wrong_format(message: types.Message):
    await message.answer("⚠️ Iltimos, coverni <b>Document</b> ko'rinishida yuboring.", parse_mode="HTML")


# ============================================================
# 4) COPYWRITER: MATNNI TOPSHIRISH
# ============================================================

@router_copy.message(F.text == "✍️ Matnni topshirish")
async def copy_done_start(message: types.Message):
    tasks = await _get_active_tasks(message.from_user.id, UserRole.copywriter)
    if not tasks:
        return await message.answer("Sizda faol vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name[:60], callback_data=f"done_c_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifa uchun matn yuborasiz?", reply_markup=kb)


@router_copy.callback_query(F.data.startswith("done_c_"))
async def copy_done_text_prompt(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)
        if not _task_owner_ok(task, UserRole.copywriter, callback.from_user.id):
            return await callback.answer("Bu vazifa sizga tegishli emas!", show_alert=True)

    await state.update_data(task_id=task_id)
    await state.set_state(ProductionStates.waiting_for_copy_text)
    await callback.message.answer("Matnni (caption) yuboring:")


@router_copy.message(ProductionStates.waiting_for_copy_text)
async def copy_done_final(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return await message.answer("⚠️ Matn bo'sh bo'lmasin.")

    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return await message.answer("Ichki xatolik: task yo'q.")

    now = datetime.now()
    async with async_session() as session:
        task = await session.get(Task, task_id)
        user = await _get_user_by_tid(session, message.from_user.id)
        if not task or not user:
            await state.clear()
            return await message.answer("Vazifa yoki foydalanuvchi topilmadi.")
        if not _task_owner_ok(task, UserRole.copywriter, user.telegram_id):
            await state.clear()
            return await message.answer("⛔ Bu vazifa sizga tegishli emas.")

        task.copy_done_at = now
        # Matnni DB'ga saqlash yo'q (modelda field yo'q). P2 refaktor bilan qo'shiladi.
        await session.commit()

    await _safe_sheet_progress(user, task, holati_text=f"Matn topshirildi {now.strftime('%d.%m %H:%M')}")
    await state.clear()
    await message.answer("✅ Matn saqlandi.")


# ============================================================
# 5) MARKETER: POSTNI NASHR ETISH VA LINK
# ============================================================

@router_mkt.message(F.text == "🚀 Postni nashr etish")
async def market_done_start(message: types.Message):
    tasks = await _get_active_tasks(message.from_user.id, UserRole.marketer)
    if not tasks:
        return await message.answer("Nashr uchun vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name[:60], callback_data=f"done_mkt_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifa linkini kiritasiz?", reply_markup=kb)


@router_mkt.callback_query(F.data.startswith("done_mkt_"))
async def market_done_link_prompt(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return await callback.answer("Vazifa topilmadi!", show_alert=True)
        if not _task_owner_ok(task, UserRole.marketer, callback.from_user.id):
            return await callback.answer("Bu vazifa sizga tegishli emas!", show_alert=True)

    await state.update_data(task_id=task_id)
    await state.set_state(ProductionStates.waiting_for_post_link)
    await callback.message.answer("Tayyor post linkini (havolasini) yuboring:")


@router_mkt.message(ProductionStates.waiting_for_post_link)
async def market_done_final(message: types.Message, state: FSMContext, bot: Bot):
    link = (message.text or "").strip()
    if "http" not in link:
        return await message.answer("⚠️ Iltimos, to'g'ri link yuboring (http/https).")

    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return await message.answer("Ichki xatolik: task yo'q.")

    now = datetime.now()
    async with async_session() as session:
        task = await session.get(Task, task_id)
        user = await _get_user_by_tid(session, message.from_user.id)
        if not task or not user:
            await state.clear()
            return await message.answer("Vazifa yoki foydalanuvchi topilmadi.")
        if not _task_owner_ok(task, UserRole.marketer, user.telegram_id):
            await state.clear()
            return await message.answer("⛔ Bu vazifa sizga tegishli emas.")

        task.final_link = link
        task.market_done_at = now
        # Admin tasdiqlaydi => Bajarildi
        task.status = "Tekshirilmoqda"
        await session.commit()

    # Marketer uchun sheets update (best-effort)
    await _safe_sheet_progress(user, task, holati_text=f"Link yuborildi {now.strftime('%d.%m %H:%M')}", status_text="Tekshirilmoqda 🔵")

    # Adminlarga yuboramiz
    kb = _admin_approval_keyboard(task.id)
    text = (
        "🏁 <b>Vazifa yakunlandi (Marketer)!</b>\n"
        f"📌 Vazifa: <b>{task.task_name}</b>\n"
        f"🆔 Task ID: <code>{task.id}</code>\n"
        f"🔗 Link: {link}\n\n"
        "Admin tasdiqlasa, link barcha ishtirokchilarning dashboardiga (AH) yoziladi."
    )
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Failed to send approval request to admin_id={admin_id}: {e}")

    await state.clear()
    await message.answer("✅ Link adminga yuborildi. Admin tasdiqlaganidan so'ng vazifa to'liq yopiladi.")