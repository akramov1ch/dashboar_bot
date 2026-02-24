from aiogram.fsm.state import StatesGroup, State

class AddEmployeeStates(StatesGroup):
    """Xodim qo'shish bosqichlari"""
    waiting_for_id = State()
    waiting_for_name = State()
    waiting_for_role = State() # Xodim turini tanlash uchun (Mobilograf, Copywriter va h.k.)

class AddAdminStates(StatesGroup):
    """Admin qo'shish bosqichlari"""
    waiting_for_id = State()
    waiting_for_name = State()

class LinkSheetStates(StatesGroup):
    """Google Sheets tabini (oyini) biriktirish bosqichlari"""
    selecting_user = State()
    waiting_for_tab_name = State()

class ContentMakerStates(StatesGroup):
    """Content Maker tomonidan vazifa yaratish bosqichlari"""
    choosing_mobilographer = State()
    writing_task_name = State()
    setting_deadline = State()
    writing_scenario = State()
    choosing_priority = State()

class ProductionStates(StatesGroup):
    """Xodimlar tomonidan ishni topshirish bosqichlari"""
    waiting_for_review_media = State() # Guruhga muhokama uchun yuborish
    waiting_for_video_file = State()   # Mobilograf uchun (Final Video)
    waiting_for_cover_file = State()   # Mobilograf uchun (Final Cover)
    waiting_for_copy_text = State()    # Copywriter uchun (Matn)
    waiting_for_design_file = State()  # Designer uchun (Tayyor Cover)
    waiting_for_post_link = State()    # Marketer uchun (Tayyor Post Linki)

class AdminFeedbackStates(StatesGroup):
    """Admin feedbacklari uchun (agar kerak bo'lsa)"""
    waiting_for_text = State()