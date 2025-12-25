from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(role: str, mode: str = "admin") -> ReplyKeyboardMarkup:
    buttons = []
    
    # --- ADMIN REJIMI ---
    if mode == "admin":
        if role == "super_admin":
            buttons = [
                [KeyboardButton(text="➕ Yangi vazifa"), KeyboardButton(text="➕ Xodim qo'shish")],
                [KeyboardButton(text="➕ Admin qo'shish"), KeyboardButton(text="📅 Yangi oy ochish")],
                [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="📊 Oylik hisobot")],
                [KeyboardButton(text="👤 Xodim rejimiga o'tish")]
            ]
        elif role in ["admin", "super_employee"]: # super_employee qo'shildi ✅
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
        # Agar foydalanuvchi adminlik huquqiga ega bo'lsa, qaytish tugmasini chiqaramiz
        if role in ["super_admin", "admin", "super_employee"]: # super_employee qo'shildi ✅
            buttons.append([KeyboardButton(text="⚙️ Admin rejimiga o'tish")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
    resize_keyboard=True
)