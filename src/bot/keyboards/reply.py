# src/bot/keyboards/reply.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu(role: str | None, user_in_db: bool = False) -> ReplyKeyboardMarkup:
    """
    Asosiy menyu.
    ✅ Designer olib tashlangan.
    """
    buttons: list[list[KeyboardButton]] = []

    # Admin panel
    if role == "admin":
        buttons = [
            [KeyboardButton(text="➕ Xodim qo'shish"), KeyboardButton(text="👥 Xodimlar")],
            [KeyboardButton(text="📊 Oylik hisobot"), KeyboardButton(text="📅 Yangi oy ochish")],
        ]

    # Content maker panel
    elif role == "content_maker":
        buttons = [
            [KeyboardButton(text="➕ Yangi vazifa")],
            [KeyboardButton(text="📊 Oylik hisobot")],
        ]

    # Ijrochilar
    elif role == "mobilographer":
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="📤 Tekshirishga yuborish"), KeyboardButton(text="✅ Bajarildi")],
        ]

    elif role == "copywriter":
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="✍️ Matnni topshirish")],
        ]

    # ✅ Designer menu yo'q

    elif role == "marketer":
        buttons = [
            [KeyboardButton(text="📝 Mening vazifalarim")],
            [KeyboardButton(text="🚀 Postni nashr etish")],
        ]

    # Agar foydalanuvchi bazada bo'lsa va admin/content_maker bo'lsa, ijrochi rejimiga o'tish tugmasi (ixtiyoriy)
    if user_in_db and role in ["admin", "content_maker"]:
        buttons.append([KeyboardButton(text="👤 Ijrochi rejimiga o'tish")])

    # Ro'yxatdan o'tmaganlar uchun bo'sh menu qaytarmaslik
    if not buttons:
        buttons = [[KeyboardButton(text="/start")]]

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
    resize_keyboard=True,
)