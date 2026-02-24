# src/services/scheduler.py

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from aiogram import Bot

from src.config import settings
from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.services.sheets_service import (
    sheets_service,
    get_next_month_name,
    replace_last_month_token,
)

logger = logging.getLogger(__name__)

# (optional) module-level reference
scheduler: AsyncIOScheduler | None = None


# =========================================================
# Helpers: role-based due dates (sizning jarayoningizga mos)
# =========================================================

def due_for_role(task: Task, role: UserRole) -> datetime:
    """
    Sizning ichki jarayon:
      - Mobilographer: yakuniy deadline - 3 kun
      - Copywriter:    yakuniy deadline - 1 kun
      - Designer:      yakuniy deadline
      - Marketer:      yakuniy deadline
    """
    if role == UserRole.mobilographer:
        return task.deadline - timedelta(days=3)
    if role == UserRole.copywriter:
        return task.deadline - timedelta(days=1)
    if role == UserRole.designer:
        return task.deadline
    if role == UserRole.marketer:
        return task.deadline
    return task.deadline


async def _safe_send(bot: Bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Send message failed chat_id={chat_id}: {e}")


# =========================================================
# ✅ Deadline reminder job (1 kun qolganda eslatadi)
# =========================================================

async def deadline_reminder_job(bot: Bot):
    """
    Har soatda ishlaydi (minute=0):
      - status != 'Bajarildi' bo'lgan vazifalarni oladi
      - har rol uchun o'z deadline (offset) bor
      - due_date'ga 1 kun qolgan oraliqda bo'lsa -> 1 marta reminder yuboradi

    Eslatma spami bo'lmasligi uchun Task modelida quyidagi flaglar bo'lishi kerak:
      - mobi_reminder_sent
      - copy_reminder_sent
      - design_reminder_sent
      - market_reminder_sent
    """
    now = datetime.now()
    window_end = now + timedelta(days=1)

    async with async_session() as session:
        tasks = (
            await session.execute(
                select(Task).where(Task.status != "Bajarildi")
            )
        ).scalars().all()

        if not tasks:
            return

        for t in tasks:
            # Mobilographer
            if t.mobilographer_id and hasattr(t, "mobi_reminder_sent"):
                due = due_for_role(t, UserRole.mobilographer)
                if (not t.mobi_reminder_sent) and (now <= due <= window_end):
                    await _safe_send(
                        bot,
                        t.mobilographer_id,
                        (
                            "⏰ <b>Deadline yaqin!</b>\n"
                            f"📌 <b>{t.task_name}</b>\n"
                            f"🗓 1 kun qoldi (Mobilograf deadline: <b>{due.strftime('%d.%m.%Y')}</b>)\n"
                            "✅ Iltimos ishni tezlashtiring."
                        ),
                    )
                    t.mobi_reminder_sent = True

            # Copywriter
            if t.copywriter_id and hasattr(t, "copy_reminder_sent"):
                due = due_for_role(t, UserRole.copywriter)
                if (not t.copy_reminder_sent) and (now <= due <= window_end):
                    await _safe_send(
                        bot,
                        t.copywriter_id,
                        (
                            "⏰ <b>Deadline yaqin!</b>\n"
                            f"📌 <b>{t.task_name}</b>\n"
                            f"🗓 1 kun qoldi (Copywriter deadline: <b>{due.strftime('%d.%m.%Y')}</b>)\n"
                            "✅ Matnni tayyorlab yuboring."
                        ),
                    )
                    t.copy_reminder_sent = True

            # Designer
            if t.designer_id and hasattr(t, "design_reminder_sent"):
                due = due_for_role(t, UserRole.designer)
                if (not t.design_reminder_sent) and (now <= due <= window_end):
                    await _safe_send(
                        bot,
                        t.designer_id,
                        (
                            "⏰ <b>Deadline yaqin!</b>\n"
                            f"📌 <b>{t.task_name}</b>\n"
                            f"🗓 1 kun qoldi (Designer deadline: <b>{due.strftime('%d.%m.%Y')}</b>)\n"
                            "✅ Coverni tayyorlab topshiring."
                        ),
                    )
                    t.design_reminder_sent = True

            # Marketer
            if t.marketer_id and hasattr(t, "market_reminder_sent"):
                due = due_for_role(t, UserRole.marketer)
                if (not t.market_reminder_sent) and (now <= due <= window_end):
                    await _safe_send(
                        bot,
                        t.marketer_id,
                        (
                            "⏰ <b>Deadline yaqin!</b>\n"
                            f"📌 <b>{t.task_name}</b>\n"
                            f"🗓 1 kun qoldi (Marketer deadline: <b>{due.strftime('%d.%m.%Y')}</b>)\n"
                            "✅ Postni chiqarish / linkni tayyorlashni unutmang."
                        ),
                    )
                    t.market_reminder_sent = True

        await session.commit()


# =========================================================
# ✅ Month rollover job (25-sanada oy + xodim tablar)
# =========================================================

async def month_rollover_job():
    """
    Har kuni belgilangan vaqtda ishga tushadi, lekin faqat AUTO_MONTH_DAY bo'lsa bajaradi:
      - OY_SHABLON -> new_month
      - XODIM_SHABLON -> "<FullName> <new_month>" har bir xodim uchun
      - users.worksheet_name yangilanadi
    """
    if not getattr(settings, "AUTO_MONTH_ROLLOVER", False):
        return

    now = datetime.now()
    if now.day != settings.AUTO_MONTH_DAY:
        return

    sheet_id = settings.DEFAULT_SPREADSHEET_ID
    new_month = get_next_month_name(now)

    # DB dan xodimlar ro'yxatini olamiz
    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.full_name))).scalars().all()
        employee_names = [u.full_name for u in users if u.full_name]

    if not employee_names:
        logger.warning("Month rollover: users not found.")
        return

    # Oy tab allaqachon mavjud bo'lsa - create skip (idempotent)
    if await sheets_service.worksheet_exists(sheet_id, new_month):
        logger.info(f"Month rollover: '{new_month}' already exists. Skipping create.")
    else:
        await sheets_service.create_month_and_employee_tabs(
            sheet_id=sheet_id,
            new_month=new_month,
            employee_full_names=employee_names
        )

    # DB worksheet_name yangilash
    async with async_session() as session:
        users = (await session.execute(select(User))).scalars().all()
        for u in users:
            if not u.full_name:
                continue
            u.worksheet_name = replace_last_month_token(u.full_name, new_month)
            if not u.personal_sheet_id:
                u.personal_sheet_id = sheet_id
        await session.commit()

    logger.info(f"✅ Month rollover completed. New month: {new_month}")


# =========================================================
# Scheduler setup (bot bilan!)
# =========================================================

def setup_scheduler(bot: Bot):
    """
    main.py da bot yaratilgandan keyin chaqiring:
        setup_scheduler(bot)
    """
    global scheduler

    tz = getattr(settings, "TIMEZONE", "Asia/Tashkent")
    scheduler = AsyncIOScheduler(timezone=tz)

    # 1) Month rollover: har kuni (soat/minute config bo'yicha)
    scheduler.add_job(
        month_rollover_job,
        CronTrigger(
            hour=settings.AUTO_MONTH_HOUR,
            minute=settings.AUTO_MONTH_MINUTE
        ),
        id="month_rollover_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # 2) Deadline reminder: har soatda (minute=0)
    scheduler.add_job(
        deadline_reminder_job,
        CronTrigger(minute=0),
        kwargs={"bot": bot},
        id="deadline_reminder_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("⏰ Scheduler started (month rollover + deadline reminders).")