from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

def get_main_menu(role: str, mode: str = "admin", user_in_db: bool = False) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    """
    Menyuni dinamik yaratish.
    
    :param role: Foydalanuvchi roli (super_admin, admin, va h.k.)
    :param mode: Qaysi rejimda ekanligi (admin yoki employee)
    :param user_in_db: Bazada bormi? (Hal qiluvchi faktor)
    """
    
    # Agar roli yo'q bo'lsa (ro'yxatdan o'tmagan va super admin ham emas)
    if not role:
        return ReplyKeyboardRemove()

    buttons = []
    
    # ==============================
    # 1. ADMIN REJIMI
    # ==============================
    if mode == "admin":
        # Hamma adminlar uchun standart tugmalar
        row1 = [KeyboardButton(text="➕ Yangi vazifa"), KeyboardButton(text="➕ Xodim qo'shish")]
        row2 = [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="📊 Oylik hisobot")]
        
        buttons.append(row1)

        # Faqat Super Admin uchun qo'shimcha tugmalar
        if role == "super_admin":
            extra_row = [KeyboardButton(text="➕ Admin qo'shish"), KeyboardButton(text="📅 Yangi oy ochish")]
            buttons.append(extra_row)
        
        buttons.append(row2)

        # --- DINAMIK TEKSHIRUV ---
        # Agar foydalanuvchi (Super Admin yoki Oddiy Admin) bazada jismonan mavjud bo'lsa,
        # unga "Xodim rejimiga o'tish" tugmasini chiqaramiz.
        if user_in_db:
            buttons.append([KeyboardButton(text="👤 Xodim rejimiga o'tish")])

    # ==============================
    # 2. XODIM REJIMI
    # ==============================
    else:
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="✅ Statusni yangilash")],
            [KeyboardButton(text="🔗 Mening Dashboardim")]
        ]
        
        # Agar adminlik huquqi bo'lsa, orqaga qaytish tugmasi doim chiqadi
        if role in ["super_admin", "admin", "super_employee"]: 
            buttons.append([KeyboardButton(text="⚙️ Admin rejimiga o'tish")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
    resize_keyboard=True
)