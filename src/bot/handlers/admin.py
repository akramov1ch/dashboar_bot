import logging
from datetime import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, update

from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.bot.states.admin_states import AddTaskStates, AddEmployeeStates, AddAdminStates, LinkSheetStates
from src.bot.keyboards.reply import get_main_menu, cancel_kb
from src.bot.filters.admin_filter import IsAnyAdminFilter
from src.services.sheets_service import sheets_service
from src.config import settings

router = Router()
router.message.filter(IsAnyAdminFilter())
logger = logging.getLogger(__name__)

priority_kb = types.ReplyKeyboardMarkup(keyboard=[
    [types.KeyboardButton(text="Muhim va tez")], 
    [types.KeyboardButton(text="Muhim lekin tez emas")],
    [types.KeyboardButton(text="Tez lekin muhim emas")], 
    [types.KeyboardButton(text="🚫 Bekor qilish")]
], resize_keyboard=True)

# =====================================================================
# YORDAMCHI FUNKSIYA (BAZADA BORLIGINI TEKSHIRISH)
# =====================================================================
async def get_db_status(telegram_id: int) -> bool:
    """
    Foydalanuvchi users jadvalida bormi?
    True -> Tugma chiqadi
    False -> Tugma chiqmaydi
    """
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return res.scalar_one_or_none() is not None

# =====================================================================
# 0. GLOBAL BEKOR QILISH
# =====================================================================

@router.message(F.text == "🚫 Bekor qilish", StateFilter('*'))
async def cancel_global(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Dinamik tekshiruv
    user_in_db = await get_db_status(message.from_user.id)
    role = "super_admin" if message.from_user.id in settings.ADMIN_IDS else "admin"
    
    await message.answer("Jarayon bekor qilindi.", reply_markup=get_main_menu(role, mode="admin", user_in_db=user_in_db))

# =====================================================================
# 1. ADMIN VA XODIM BOSHQARUVI
# =====================================================================

@router.message(F.text == "➕ Admin qo'shish")
async def cmd_add_admin(message: types.Message, state: FSMContext):
    if message.from_user.id not in settings.ADMIN_IDS: return await message.answer("⛔️ Faqat Super Admin uchun!")
    await state.clear()
    await message.answer("Yangi Admin ID raqamini yuboring:", reply_markup=cancel_kb)
    await state.set_state(AddAdminStates.waiting_for_id)

@router.message(AddAdminStates.waiting_for_id)
async def process_admin_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ ID raqam bo'lsin!")
    await state.update_data(new_admin_id=int(message.text))
    await state.set_state(AddAdminStates.waiting_for_name)
    await message.answer("Ism va Familiyasini yozing:", reply_markup=cancel_kb)

@router.message(AddAdminStates.waiting_for_name)
async def process_admin_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['new_admin_id']
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        if user:
            user.full_name = message.text
            user.role = UserRole.super_employee if user.role == UserRole.employee else UserRole.admin
            msg = f"✅ <b>{message.text}</b> huquqlari yangilandi."
        else:
            new_admin = User(telegram_id=user_id, full_name=message.text, role=UserRole.admin, personal_sheet_id=settings.DEFAULT_SPREADSHEET_ID)
            session.add(new_admin)
            msg = f"✅ Yangi Admin qo'shildi: <b>{message.text}</b>"
        await session.commit()
    
    await state.clear()
    
    # Dinamik tekshiruv
    user_in_db = await get_db_status(message.from_user.id)
    await message.answer(msg, reply_markup=get_main_menu("super_admin", mode="admin", user_in_db=user_in_db), parse_mode="HTML")

@router.message(F.text == "➕ Xodim qo'shish")
async def cmd_add_employee(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Xodim ID raqamini yuboring:", reply_markup=cancel_kb)
    await state.set_state(AddEmployeeStates.waiting_for_id)

@router.message(AddEmployeeStates.waiting_for_id)
async def process_emp_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ ID raqam bo'lsin!")
    await state.update_data(new_id=int(message.text))
    await state.set_state(AddEmployeeStates.waiting_for_name)
    await message.answer("Ism va Familiyasini yozing:", reply_markup=cancel_kb)

@router.message(AddEmployeeStates.waiting_for_name)
async def process_emp_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == data['new_id']))
        user = res.scalar_one_or_none()
        if user:
            user.full_name = message.text
            if user.role == UserRole.admin: user.role = UserRole.super_employee
            msg = f"🔄 <b>{message.text}</b> ma'lumotlari yangilandi."
        else:
            new_user = User(telegram_id=data['new_id'], full_name=message.text, role=UserRole.employee, personal_sheet_id=settings.DEFAULT_SPREADSHEET_ID)
            session.add(new_user)
            msg = f"✅ Xodim qo'shildi: <b>{message.text}</b>"
        await session.commit()
    
    await state.clear()
    
    # Dinamik tekshiruv (Eng muhim joyi: agar o'zini qo'shgan bo'lsa, tugma chiqadi)
    user_in_db = await get_db_status(message.from_user.id)
    role = "super_admin" if message.from_user.id in settings.ADMIN_IDS else "admin"
    
    await message.answer(msg, reply_markup=get_main_menu(role, mode="admin", user_in_db=user_in_db), parse_mode="HTML")

# =====================================================================
# 2. VAZIFA YUKLASH
# =====================================================================

@router.message(F.text == "➕ Yangi vazifa")
async def cmd_add_task(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        # Bu ro'yxatda kim chiqishi. Tugmaga aloqasi yo'q.
        # Super Adminlar agar ro'yxatda chiqmasligi kerak bo'lsa:
        res = await session.execute(
            select(User).where(
                User.role.in_([UserRole.employee, UserRole.admin, UserRole.super_employee]),
                ~User.telegram_id.in_(settings.ADMIN_IDS) # <-- Super Adminlar ro'yxatda yashirin
            )
        )
        users = res.scalars().all()
    if not users: return await message.answer("Vazifa berish uchun xodimlar yo'q.")
    kb = types.ReplyKeyboardMarkup(keyboard=[[types.KeyboardButton(text=u.full_name)] for u in users] + [[types.KeyboardButton(text="🚫 Bekor qilish")]], resize_keyboard=True)
    await state.set_state(AddTaskStates.choosing_employee)
    await message.answer("Kimga vazifa beramiz?", reply_markup=kb)

@router.message(AddTaskStates.choosing_employee)
async def process_task_emp(message: types.Message, state: FSMContext):
    await state.update_data(emp_name=message.text)
    await state.set_state(AddTaskStates.writing_task)
    await message.answer(f"<b>{message.text}</b> uchun vazifa matnini yozing:", reply_markup=cancel_kb, parse_mode="HTML")

@router.message(AddTaskStates.writing_task)
async def process_task_text(message: types.Message, state: FSMContext):
    await state.update_data(task_name=message.text)
    await state.set_state(AddTaskStates.setting_deadline)
    await message.answer("Muddat (masalan: 25.12.2025):", reply_markup=cancel_kb)

@router.message(AddTaskStates.setting_deadline)
async def process_task_deadline(message: types.Message, state: FSMContext):
    await state.update_data(deadline=message.text)
    await state.set_state(AddTaskStates.choosing_priority)
    await message.answer("Muhimlik darajasini tanlang:", reply_markup=priority_kb)

@router.message(AddTaskStates.choosing_priority)
async def process_task_final(message: types.Message, state: FSMContext, bot: Bot):
    priority = message.text
    data = await state.get_data()
    async with async_session() as session:
        res = await session.execute(select(User).where(User.full_name == data['emp_name']))
        emp = res.scalar_one_or_none()
        
        if not emp:
            await state.clear()
            return await message.answer("❌ Xatolik: Foydalanuvchi topilmadi. Iltimos, qaytadan boshlang.")

        try:
            row_idx = await sheets_service.add_task_to_sheet(emp.personal_sheet_id, emp.worksheet_name, data['task_name'], data['deadline'], priority)
            new_task = Task(user_id=emp.id, assigner_id=message.from_user.id, task_name=data['task_name'], deadline=data['deadline'], status="Yangi", row_index=row_idx)
            session.add(new_task)
            await session.commit()
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Vazifani qabul qildim", callback_data=f"accept_task_{new_task.id}")]])
            await bot.send_message(emp.telegram_id, f"📩 <b>Yangi vazifa yuklatildi!</b>\n\n📌 <b>Vazifa:</b> {data['task_name']}\n📅 <b>Muddat:</b> {data['deadline']}\n📊 <b>Daraja:</b> {priority}", reply_markup=kb, parse_mode="HTML")
            
            # Dinamik tekshiruv
            user_in_db = await get_db_status(message.from_user.id)
            role = "super_admin" if message.from_user.id in settings.ADMIN_IDS else "admin"
            await message.answer("✅ Vazifa yozildi va xodimga bildirildi!", reply_markup=get_main_menu(role, mode="admin", user_in_db=user_in_db))
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")
        finally:
            await state.clear()

# =====================================================================
# 3. FEEDBACK VA APPROVE
# =====================================================================

async def save_admin_feedback(task_id, admin_user, text, bot: Bot):
    async with async_session() as session:
        res = await session.execute(select(Task).where(Task.id == task_id))
        task = res.scalar_one_or_none()
        if not task: return
        
        fbs = dict(task.feedbacks) if task.feedbacks else {}
        fbs[str(admin_user.id)] = {"name": admin_user.full_name, "text": text}
        task.feedbacks = fbs
        await session.commit()
        await session.refresh(task)
        
        res_count = await session.execute(select(User).where(User.role.in_([UserRole.admin, UserRole.super_employee]), ~User.telegram_id.in_(settings.ADMIN_IDS), User.id != task.user_id))
        total_eligible = len(res_count.scalars().all())
        
        if len(task.feedbacks) >= total_eligible:
            await notify_super_admin_final(task, bot)

async def notify_super_admin_final(task, bot: Bot):
    async with async_session() as session:
        res = await session.execute(select(Task).where(Task.id == task.id))
        task = res.scalar_one_or_none()
        if not task: return
        user = await session.get(User, task.user_id)
        fb_summary = "\n".join([f"• <b>{v['name']}</b>: {v['text']}" for v in task.feedbacks.values()]) if task.feedbacks else "Feedbacklar yo'q."
        text = f"🏁 <b>Vazifa yakuniy tekshiruvga tayyor!</b>\n📌: {task.task_name}\n👤: {user.full_name}\n\n💬 <b>Feedbacklar:</b>\n{fb_summary}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"super_approve_{task.id}"), InlineKeyboardButton(text="❌ Qaytarish", callback_data=f"super_reject_{task.id}")]])
        for s_id in settings.ADMIN_IDS:
            try: await bot.send_message(s_id, text, reply_markup=kb, parse_mode="HTML")
            except: pass

@router.callback_query(F.data.startswith("super_approve_"))
async def super_approve(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    task_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        task = await session.get(Task, task_id)
        user = await session.get(User, task.user_id)
        try:
            deadline_dt = datetime.strptime(task.deadline.strip(), "%d.%m.%Y").date()
            is_late = datetime.now().date() > deadline_dt
        except: is_late = False
        
        final_status = "Kech qabul qilindi 🔴" if is_late else "Qabul qilindi 🟢"
        await sheets_service.update_task_columns(user.personal_sheet_id, user.worksheet_name, task.row_index, status=final_status)
        task.status = "Bajarildi"
        await session.commit()
        
        await bot.send_message(user.telegram_id, f"🎉 Vazifangiz qabul qilindi!\n📌 {task.task_name}\nStatus: {final_status}")
        
        await state.update_data(super_fb_task_id=task_id)
        await state.set_state(AddAdminStates.waiting_for_super_feedback)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ Yo'q, shartmas", callback_data="super_fb_skip")]])
        await callback.message.edit_text(f"✅ Vazifa qabul qilindi ({final_status}).\n\n<b>Endi Direktor izohini (AL38) yozasizmi?</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("super_reject_"))
async def super_reject(callback: types.CallbackQuery, bot: Bot):
    task_id = int(callback.data.split("_")[2])
    async with async_session() as session:
        task = await session.get(Task, task_id)
        user = await session.get(User, task.user_id)
        await sheets_service.update_task_columns(user.personal_sheet_id, user.worksheet_name, task.row_index, holati="Jarayonda", status="Qabul qilinmadi 🔴")
        task.status = "Jarayonda"
        task.feedbacks = {}
        await session.commit()
        await bot.send_message(user.telegram_id, f"⚠️ Vazifangiz rad etildi va qaytarildi: {task.task_name}")
    await callback.message.edit_text("🔴 Vazifa rad etildi va xodimga qaytarildi.")

@router.message(AddAdminStates.waiting_for_super_feedback)
async def process_super_feedback(message: types.Message, state: FSMContext):
    if message.text in ["➕ Yangi vazifa", "➕ Xodim qo'shish", "👥 Xodimlar", "📊 Oylik hisobot", "📅 Yangi oy ochish"]:
        await state.clear()
        return await message.answer("⚠️ Avvalgi jarayon yakunlanmagan edi. Holat tozalandi. Iltimos, tugmani qayta bosing.")

    data = await state.get_data()
    async with async_session() as session:
        task = await session.get(Task, data['super_fb_task_id'])
        user = await session.get(User, task.user_id)
        await sheets_service.update_direktor_feedback(user.personal_sheet_id, user.worksheet_name, task.row_index, message.text)
    await state.clear()
    
    # Dinamik tekshiruv
    user_in_db = await get_db_status(message.from_user.id)
    await message.answer("✅ Direktor izohi AL38 ustuniga yozildi!", reply_markup=get_main_menu("super_admin", mode="admin", user_in_db=user_in_db))

@router.callback_query(F.data == "super_fb_skip")
async def super_fb_skip(callback: types.CallbackQuery):
    await callback.message.edit_text("✅ Jarayon yakunlandi (Izohsiz).")

# --- BOSHQA ---
@router.message(F.text == "👥 Xodimlar")
async def cmd_list(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        # SUPER ADMINLAR RO'YXATDA YASHIRILDI
        res = await session.execute(
            select(User).where(
                User.role.in_([UserRole.employee, UserRole.admin, UserRole.super_employee]),
                ~User.telegram_id.in_(settings.ADMIN_IDS)
            )
        )
        users = res.scalars().all()
    
    if not users:
        text = "👥 Hozircha xodimlar yo'q."
    else:
        text = "<b>👥 Xodimlar ro'yxati:</b>\n\n" + "\n".join([f"• {u.full_name} ({u.role.value})" for u in users])
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "📊 Oylik hisobot")
async def cmd_report(message: types.Message, state: FSMContext):
    await state.clear()
    link = f"https://docs.google.com/spreadsheets/d/{settings.DEFAULT_SPREADSHEET_ID}"
    await message.answer(f"📊 <a href='{link}'>Dashboardni ochish</a>", parse_mode="HTML", disable_web_page_preview=True)

@router.message(F.text == "📅 Yangi oy ochish")
async def cmd_link_sheet(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        # SUPER ADMINLAR YASHIRILDI
        res = await session.execute(
            select(User).where(
                User.role.in_([UserRole.employee, UserRole.admin, UserRole.super_employee]),
                ~User.telegram_id.in_(settings.ADMIN_IDS)
            )
        )
        users = res.scalars().all()
    kb = types.ReplyKeyboardMarkup(keyboard=[[types.KeyboardButton(text=u.full_name)] for u in users] + [[types.KeyboardButton(text="🚫 Bekor qilish")]], resize_keyboard=True)
    await state.set_state(LinkSheetStates.selecting_user)
    await message.answer("Foydalanuvchini tanlang:", reply_markup=kb)

@router.message(LinkSheetStates.selecting_user)
async def process_link_user(message: types.Message, state: FSMContext):
    await state.update_data(target_name=message.text)
    await state.set_state(LinkSheetStates.waiting_for_tab_name)
    await message.answer(f"{message.text} uchun Tab nomini yozing:", reply_markup=cancel_kb)

@router.message(LinkSheetStates.waiting_for_tab_name)
async def process_tab_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        await session.execute(update(User).where(User.full_name == data['target_name']).values(worksheet_name=message.text))
        await session.commit()
    await state.clear()
    
    # Dinamik tekshiruv
    user_in_db = await get_db_status(message.from_user.id)
    role = "super_admin" if message.from_user.id in settings.ADMIN_IDS else "admin"
    await message.answer(f"✅ Tab bog'landi: {message.text}", reply_markup=get_main_menu(role, mode="admin", user_in_db=user_in_db))

async def notify_admins_for_feedback(task, user, bot: Bot):
    async with async_session() as session:
        res = await session.execute(select(User).where(User.role.in_([UserRole.admin, UserRole.super_employee]), ~User.telegram_id.in_(settings.ADMIN_IDS), User.id != task.user_id))
        admins = res.scalars().all()
        if not admins:
            await notify_super_admin_final(task, bot)
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ha, yozaman", callback_data=f"fb_yes_{task.id}"),
             InlineKeyboardButton(text="⏭ Yo'q, shartmas", callback_data=f"fb_no_{task.id}")]
        ])
        for admin in admins:
            try: await bot.send_message(admin.telegram_id, f"📝 <b>Vazifa bajarildi:</b> {task.task_name}\n👤 Xodim: {user.full_name}\nFeedback yozasizmi?", reply_markup=kb, parse_mode="HTML")
            except: pass