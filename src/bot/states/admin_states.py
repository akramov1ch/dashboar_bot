from aiogram.fsm.state import StatesGroup, State

class AddTaskStates(StatesGroup):
    """Vazifa qo'shish bosqichlari"""
    choosing_employee = State()
    writing_task = State()
    setting_deadline = State()
    choosing_priority = State()

class AddEmployeeStates(StatesGroup):
    """Xodim qo'shish bosqichlari"""
    waiting_for_id = State()
    waiting_for_name = State()

class AddAdminStates(StatesGroup):
    """Admin qo'shish va Super Admin feedback bosqichlari"""
    waiting_for_id = State()
    waiting_for_name = State()
    waiting_for_super_feedback = State() # Super Admin izohi uchun ✅

class LinkSheetStates(StatesGroup):
    """Tab biriktirish bosqichlari"""
    selecting_user = State()
    waiting_for_tab_name = State()