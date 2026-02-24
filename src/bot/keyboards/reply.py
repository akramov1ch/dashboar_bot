from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

def get_main_menu(role: str, user_in_db: bool = False) -> ReplyKeyboardMarkup:
    buttons = []
    
    # Admin va Content Maker vazifa boshqaruvchilari
    if role == "admin":
        buttons = [
            [KeyboardButton(text="➕ Xodim qo'shish"), KeyboardButton(text="👥 Xodimlar")],
            [KeyboardButton(text="📊 Oylik hisobot"), KeyboardButton(text="📅 Yangi oy ochish")]
        ]
    elif role == "content_maker":
        buttons = [
            [KeyboardButton(text="➕ Yangi vazifa")],
            [KeyboardButton(text="📊 Oylik hisobot")]
        ]
    
    # Ijrochilar
    elif role == "mobilographer":
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="📤 Tekshirishga yuborish"), KeyboardButton(text="✅ Bajarildi")]
        ]
    
    elif role == "copywriter":
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="✍️ Matnni topshirish")]
        ]
    
    elif role == "designer":
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="🎨 Coverni topshirish")]
        ]
    
    elif role == "marketer":
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="🚀 Postni nashr etish")]
        ]

    # Agar foydalanuvchi bazada bo'lsa va admin bo'lmasa, rejimlar orasida o'tish tugmasi (ixtiyoriy)
    if user_in_db and role in ["admin", "content_maker"]:
        buttons.append([KeyboardButton(text="👤 Ijrochi rejimiga o'tish")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
    resize_keyboard=True
)