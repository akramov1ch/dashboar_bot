from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.services.sheets_service import sheets_service
from src.config import settings
import logging

router = Router()
logger = logging.getLogger(__name__)

async def sync_tasks_with_sheet(user, session):
    """Google Sheets'dan o'chirilgan vazifalarni bazadan ham o'chirish va qatorlarni yangilash"""
    try:
        # 1. Sheets'dagi barcha qatorlarni olamiz
        sheet_rows = await sheets_service.get_all_rows(user.personal_sheet_id, user.worksheet_name)
        
        # 2. Bazadagi ushbu xodimga tegishli faol vazifalarni olamiz
        res = await session.execute(
            select(Task).where(Task.user_id == user.id, Task.status != "Bajarildi")
        )
        db_tasks = res.scalars().all()

        for task in db_tasks:
            found = False
            new_row_index = -1
            
            # Sheets'dan ushbu vazifani nomi bo'yicha qidiramiz (B ustuni - index 1)
            for idx, row in enumerate(sheet_rows, 1):
                if len(row) > 1 and row[1].strip() == task.task_name.strip():
                    found = True
                    new_row_index = idx
                    break
            
            if not found:
                # Agar Sheets'da o'chirilgan bo'lsa, bazadan ham o'chiramiz
                await session.delete(task)
                logger.info(f"Vazifa bazadan o'chirildi (Sheets'da yo'q): {task.task_name}")
            else:
                # Agar bo'lsa, qator raqamini yangilaymiz (chunki qatorlar surilgan bo'lishi mumkin)
                task.row_index = new_row_index
        
        await session.commit()
    except Exception as e:
        logger.error(f"Sinxronizatsiya xatosi: {e}")

@router.message(F.text == "✅ Statusni yangilash")
async def cmd_update_status(message: types.Message):
    async with async_session() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_res.scalar_one_or_none()
        if not user: return await message.answer("Siz ro'yxatdan o'tmagansiz.")
        
        # AVVAL SINXRONIZATSIYA QILAMIZ ✅
        await sync_tasks_with_sheet(user, session)
        
        # Keyin tozalangan ro'yxatni bazadan olamiz
        tasks_res = await session.execute(
            select(Task).where(Task.user_id == user.id, Task.status != "Bajarildi")
        )
        tasks = tasks_res.scalars().all()

    if not tasks:
        return await message.answer("Sizda hozircha faol vazifalar yo'q. ✅")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📌 {t.task_name[:25]}", callback_data=f"select_task_status_{t.id}")] for t in tasks
    ])
    
    await message.answer("Qaysi vazifaning holatini o'zgartirmoqchisiz?", reply_markup=kb)

@router.callback_query(F.data.startswith("select_task_status_"))
async def process_task_selection(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[3])
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task: return await callback.answer("Vazifa topilmadi!")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏳ Jarayonda", callback_data=f"set_prog_jarayon_{task.id}")],
            [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"set_prog_bajarildi_{task.id}")],
            [InlineKeyboardButton(text="❌ Resurs yo'qligi", callback_data=f"set_prog_resurs_{task.id}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_tasks")]
        ])
        
        await callback.message.edit_text(
            f"📌 <b>Vazifa:</b> {task.task_name}\n\nUshbu vazifa uchun yangi holatni tanlang:",
            reply_markup=kb,
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("set_prog_"))
async def process_status_change(callback: types.CallbackQuery, bot: Bot):
    _, _, state_val, task_id = callback.data.split("_")
    status_map = {"jarayon": "Jarayonda", "bajarildi": "Bajarildi", "resurs": "Resurs yo'qligi"}
    holati = status_map[state_val]

    async with async_session() as session:
        task = await session.get(Task, int(task_id))
        if not task: return await callback.answer("Vazifa topilmadi!")
        user = await session.get(User, task.user_id)
        
        if state_val == "bajarildi":
            # AC -> Tekshirilmoqda, M -> Bajarildi
            await sheets_service.update_task_columns(user.personal_sheet_id, user.worksheet_name, task.row_index, holati="Bajarildi", status="Tekshirilmoqda 🔵")
            task.status = "Tekshirilmoqda"
            await session.commit()
            
            from src.bot.handlers.admin import notify_admins_for_feedback
            await notify_admins_for_feedback(task, user, bot)
            await callback.message.edit_text(f"✅ Vazifa yakunlandi va tekshiruvga yuborildi.")
        else:
            await sheets_service.update_task_columns(user.personal_sheet_id, user.worksheet_name, task.row_index, holati=holati)
            task.status = holati
            await session.commit()
            await callback.message.edit_text(f"✅ Vazifa holati '<b>{holati}</b>'ga o'zgartirildi.", parse_mode="HTML")

@router.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: types.CallbackQuery):
    await callback.message.delete()
    await cmd_update_status(callback.message)

@router.message(F.text == "📝 Mening vazifalarim")
async def cmd_my_tasks(message: types.Message):
    async with async_session() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_res.scalar_one_or_none()
        if not user: return await message.answer("Ro'yxatdan o'tmagansiz.")
        
        # AVVAL SINXRONIZATSIYA QILAMIZ ✅
        await sync_tasks_with_sheet(user, session)
        
        tasks_res = await session.execute(select(Task).where(Task.user_id == user.id, Task.status != "Bajarildi"))
        tasks = tasks_res.scalars().all()
    
    if not tasks: return await message.answer("Sizda faol vazifalar yo'q. ✅")
    text = "📝 <b>Sizning vazifalaringiz:</b>\n\n" + "\n".join([f"{i+1}. {t.task_name} (Holati: {t.status})" for i, t in enumerate(tasks)])
    await message.answer(text, parse_mode="HTML")

@router.callback_query(F.data.startswith("accept_task_"))
async def accept_task(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task: return await callback.answer("Vazifa topilmadi!")
        user = await session.get(User, task.user_id)
        await sheets_service.update_task_columns(user.personal_sheet_id, user.worksheet_name, task.row_index, holati="Ishni boshlamoqchiman")
        task.status = "Ishni boshlamoqchiman"
        await session.commit()
    await callback.message.edit_text("✅ Vazifani qabul qildingiz. Ishga muvaffaqiyat!")