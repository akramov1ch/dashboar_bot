from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_status_keyboard(task_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"set_done_{task_id}")],
        [InlineKeyboardButton(text="⏳ Jarayonda", callback_data=f"set_process_{task_id}")],
        [InlineKeyboardButton(text="❌ Resurs yo'q", callback_data=f"set_nores_{task_id}")]
    ])