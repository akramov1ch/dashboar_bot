from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

def get_main_menu(role: str, mode: str = "admin") -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    # Agar rol berilmagan bo'lsa (ro'yxatdan o'tmagan user)
    if not role:
        return ReplyKeyboardRemove()

    buttons = []
    
    # --- ADMIN REJIMI ---
    if mode == "admin":
        if role == "super_admin":
            # Super Adminga xodim rejimi kerak emas
            buttons = [
                [KeyboardButton(text="➕ Yangi vazifa"), KeyboardButton(text="➕ Xodim qo'shish")],
                [KeyboardButton(text="➕ Admin qo'shish"), KeyboardButton(text="📅 Yangi oy ochish")],
                [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="📊 Oylik hisobot")]
            ]
        elif role in ["admin", "super_employee"]: 
            # Oddiy admin va super xodimda bu tugma bo'lishi mumkin
            buttons = [
                [KeyboardButton(text="➕ Yangi vazifa"), KeyboardButton(text="➕ Xodim qo'shish")],
                [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="📊 Oylik hisobot")],
                [KeyboardButton(text="👤 Xodim rejimiga o'tish")]
            ]
        else:
            return get_main_menu(role, mode="employee")

    # --- XODIM REJIMI ---
    else:
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="✅ Statusni yangilash")],
            [KeyboardButton(text="🔗 Mening Dashboardim")]
        ]
        # Agar foydalanuvchi oddiy admin bo'lsa, ortga qaytish chiqadi
        if role in ["admin", "super_employee"]: 
            buttons.append([KeyboardButton(text="⚙️ Admin rejimiga o'tish")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
    resize_keyboard=True
)