# src/bot/handlers/production.py
#
# Designer oqimi olib tashlangan ✅
# Mobilograf cover faylni topshirganda endi marketerga yuboriladi ✅

import logging
from datetime import datetime

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.services.sheets_service import sheets_service
from src.bot.states.admin_states import ProductionStates
from src.config import settings

router = Router()
logger = logging.getLogger(__name__)


# =========================================================
# Helper: rol bo'yicha faol vazifalarni olish
# =========================================================
async def get_active_tasks(user_id: int, role: UserRole):
    async with async_session() as session:
        if role == UserRole.mobilographer:
            res = await session.execute(
                select(Task).where(
                    Task.mobilographer_id == user_id,
                    Task.status != "Bajarildi"
                )
            )
        elif role == UserRole.copywriter:
            res = await session.execute(
                select(Task).where(
                    Task.copywriter_id == user_id,
                    Task.status != "Bajarildi"
                )
            )
        elif role == UserRole.marketer:
            res = await session.execute(
                select(Task).where(
                    Task.marketer_id == user_id,
                    Task.status != "Bajarildi"
                )
            )
        else:
            return []
        return res.scalars().all()


# =========================================================
# 1) MOBILOGRAF: MUHOKAMA GURUHIGA YUBORISH
# =========================================================
@router.message(F.text == "📤 Tekshirishga yuborish")
async def mobi_review_start(message: types.Message):
    tasks = await get_active_tasks(message.from_user.id, UserRole.mobilographer)
    if not tasks:
        return await message.answer("Sizda faol vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name, callback_data=f"rev_m_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifani muhokama guruhiga yubormoqchisiz?", reply_markup=kb)


@router.callback_query(F.data.startswith("rev_m_"))
async def mobi_review_media(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(task_id=int(callback.data.split("_")[2]))
    await state.set_state(ProductionStates.waiting_for_review_media)
    await callback.message.answer("Vazifa mediasini (video/rasm) yuboring:")


@router.message(ProductionStates.waiting_for_review_media)
async def mobi_review_to_group(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    group_id = settings.GROUP_ID

    try:
        await bot.send_message(
            group_id,
            (
                "🎬 <b>Muhokama uchun media</b>\n"
                f"👤 Kimdan: {message.from_user.full_name}\n"
                f"📌 Vazifa ID: {data['task_id']}"
            ),
            parse_mode="HTML"
        )
        await message.copy_to(group_id)
    except Exception as e:
        logger.error(f"Group review send error: {e}")
        await state.clear()
        return await message.answer("❌ Guruhga yuborishda xatolik. GROUP_ID va bot huquqlarini tekshiring.")

    await state.clear()
    await message.answer(
        "✅ Media guruhga yuborildi. Muhokamadan so'ng '✅ Bajarildi' tugmasi orqali yakuniy fayllarni topshiring."
    )


# =========================================================
# 2) MOBILOGRAF: BAJARILDI (VIDEO + COVER)
#    Cover endi marketerga yuboriladi ✅
# =========================================================
@router.message(F.text == "✅ Bajarildi")
async def mobi_done_start(message: types.Message):
    tasks = await get_active_tasks(message.from_user.id, UserRole.mobilographer)
    if not tasks:
        return await message.answer("Sizda faol vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name, callback_data=f"done_m_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifani yakunlamoqchisiz?", reply_markup=kb)


@router.callback_query(F.data.startswith("done_m_"))
async def mobi_done_video(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(task_id=int(callback.data.split("_")[2]))
    await state.set_state(ProductionStates.waiting_for_video_file)
    await callback.message.answer(
        "Sifatni saqlash uchun <b>Video faylni</b> (Document ko'rinishida) yuboring:",
        parse_mode="HTML"
    )


@router.message(ProductionStates.waiting_for_video_file, F.document)
async def mobi_done_cover(message: types.Message, state: FSMContext):
    await state.update_data(video_file_id=message.document.file_id)
    await state.set_state(ProductionStates.waiting_for_cover_file)
    await message.answer(
        "Endi <b>Cover rasmini</b> fayl formatida (Document) yuboring:",
        parse_mode="HTML"
    )


@router.message(ProductionStates.waiting_for_cover_file, F.document)
async def mobi_done_final(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()

    async with async_session() as session:
        task = await session.get(Task, data["task_id"])
        if not task:
            await state.clear()
            return await message.answer("❌ Vazifa topilmadi.")

        user_res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_res.scalar_one_or_none()
        if not user:
            await state.clear()
            return await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")

        # Marketerni topamiz (designer yo'q ✅)
        marketer_res = await session.execute(select(User).where(User.role == UserRole.marketer))
        marketer = marketer_res.scalars().first()

        now = datetime.now()
        task.mobi_done_at = now

        # Sheets: M (13) va AC (29) ustunlari
        try:
            await sheets_service.update_progress_status(
                user.personal_sheet_id,
                user.worksheet_name,
                task.row_index,
                f"Bajarildi {now.strftime('%d.%m %H:%M')}",
                "Tekshirilmoqda 🔵"
            )
        except Exception as e:
            logger.error(f"Sheets update_progress_status error: {e}")

        # ✅ Cover marketerga yuboriladi
        if marketer:
            task.marketer_id = marketer.telegram_id

            try:
                await bot.send_document(
                    marketer.telegram_id,
                    message.document.file_id,
                    caption=(
                        "🚀 <b>Yangi post vazifasi!</b>\n"
                        f"📌 Vazifa: <b>{task.task_name}</b>\n"
                        f"📅 Deadline: <b>{task.deadline.strftime('%d.%m.%Y')}</b>\n\n"
                        "Mobilograf cover faylni yukladi. "
                        "Iltimos postni tayyorlab nashr qiling va linkni botga yuboring."
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Marketer send_document error: {e}")
        else:
            logger.warning("Marketer topilmadi (bazada yo'q).")

        await session.commit()

    await state.clear()
    await message.answer("✅ Video va Cover qabul qilindi. Cover marketerga yuborildi.")


# =========================================================
# 3) COPYWRITER: MATNNI TOPSHIRISH
# =========================================================
@router.message(F.text == "✍️ Matnni topshirish")
async def copy_done_start(message: types.Message):
    tasks = await get_active_tasks(message.from_user.id, UserRole.copywriter)
    if not tasks:
        return await message.answer("Sizda faol vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name, callback_data=f"done_c_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifa uchun matn yuborasiz?", reply_markup=kb)


@router.callback_query(F.data.startswith("done_c_"))
async def copy_done_text(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(task_id=int(callback.data.split("_")[2]))
    await state.set_state(ProductionStates.waiting_for_copy_text)
    await callback.message.answer("Matnni (caption) yuboring:")


@router.message(ProductionStates.waiting_for_copy_text)
async def copy_done_final(message: types.Message, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        task = await session.get(Task, data["task_id"])
        if not task:
            await state.clear()
            return await message.answer("❌ Vazifa topilmadi.")

        task.copy_done_at = datetime.now()
        await session.commit()

    await state.clear()
    await message.answer("✅ Matn saqlandi.")


# =========================================================
# 4) MARKETER: POSTNI NASHR ETISH VA LINK YUBORISH
# =========================================================
@router.message(F.text == "🚀 Postni nashr etish")
async def market_done_start(message: types.Message):
    tasks = await get_active_tasks(message.from_user.id, UserRole.marketer)
    if not tasks:
        return await message.answer("Nashr uchun vazifalar yo'q.")

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t.task_name, callback_data=f"done_mkt_{t.id}")]
        for t in tasks
    ])
    await message.answer("Qaysi vazifa linkini kiritasiz?", reply_markup=kb)


@router.callback_query(F.data.startswith("done_mkt_"))
async def market_done_link(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(task_id=int(callback.data.split("_")[2]))
    await state.set_state(ProductionStates.waiting_for_post_link)
    await callback.message.answer("Tayyor post linkini (havolasini) yuboring:")


@router.message(ProductionStates.waiting_for_post_link, F.text.contains("http"))
async def market_done_final(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    task_id = data["task_id"]
    link = message.text.strip()

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            await state.clear()
            return await message.answer("❌ Vazifa topilmadi.")

        task.final_link = link
        task.market_done_at = datetime.now()

        # Adminlarga tasdiqlash uchun yuborish
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"adm_app_{task.id}"),
                types.InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_rej_{task.id}"),
            ]
        ])

        sent_count = 0
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    (
                        "🏁 <b>Vazifa yakunlandi!</b>\n"
                        f"📌 Vazifa: <b>{task.task_name}</b>\n"
                        f"🔗 Link: {link}\n\n"
                        "Admin tasdiqlasa, link barcha xodimlarning dashboardiga yoziladi."
                    ),
                    reply_markup=kb,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Admin notify error admin_id={admin_id}: {e}")

        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Link adminga yuborildi ({sent_count} ta admin). Admin tasdiqlaganidan so'ng vazifa to'liq yopiladi."
    )