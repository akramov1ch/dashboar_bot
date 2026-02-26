# src/services/scheduler.py
#
# ✅ Oylarni avtomatik ochish (har oy 25-kun)
# ✅ Deadline eslatma (deadline'ga 1 kun qolганда) — mobilographer/copywriter/marketer
# ✅ Designer yo'q (butunlay olib tashlangan)
# ✅ Bot object main.py dan setup_scheduler(bot) orqali uzatiladi
#
# Talab qilinadigan .env (settings):
# - TIMEZONE=Asia/Tashkent
# - AUTO_MONTH_ROLLOVER=true
# - AUTO_MONTH_DAY=25
# - AUTO_MONTH_HOUR=9
# - AUTO_MONTH_MINUTE=0
# - GROUP_ID=-100...
#
# Eslatma:
# - Task modelda reminder flaglar bo'lsa ideal:
#   mobi_reminder_sent, copy_reminder_sent, market_reminder_sent (Boolean default False)
#   Agar yo'q bo'lsa, scheduler spammasligi uchun "best-effort" ishlaydi (log beradi).

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from src.config import settings
from src.database.base import async_session
from src.database.models import User, Task, UserRole
from src.services.sheets_service import sheets_service

logger = logging.getLogger(__name__)


def _get_timezone():
    # settings.TIMEZONE bo'lmasa fallback
    return getattr(settings, "TIMEZONE", "Asia/Tashkent")


# =========================================================
# JOB 1: Deadline reminder (deadline'ga 1 kun qolганда)
# =========================================================
async def job_deadline_reminders(bot):
    """
    Deadline eslatmalari:
    - Task.deadline bilan hozir orasida ~1 kun qolsa eslatadi
    - Har userga bir marta yuborish uchun Task'da flaglar bo'lishi tavsiya.
    """
    now = datetime.now()
    target_start = now + timedelta(hours=23)
    target_end = now + timedelta(hours=25)

    async with async_session() as session:
        # Bajarilmagan tasklar
        res = await session.execute(
            select(Task).where(Task.status != "Bajarildi")
        )
        tasks = res.scalars().all()

        if not tasks:
            return

        for task in tasks:
            if not task.deadline:
                continue

            # 1 kun oynasi ichida bo'lsa
            if not (target_start <= task.deadline <= target_end):
                continue

            # Mobilographer reminder
            await _send_role_reminder_if_needed(
                session=session,
                bot=bot,
                task=task,
                role="mobilographer",
                user_telegram_id=task.mobilographer_id,
                flag_attr="mobi_reminder_sent",
                message_text=(
                    "⏰ <b>Eslatma!</b>\n"
                    f"📌 Vazifa: <b>{task.task_name}</b>\n"
                    "Deadline 1 kun qoldi. Iltimos, ishni yakunlang."
                ),
            )

            # Copywriter reminder
            if task.copywriter_id:
                await _send_role_reminder_if_needed(
                    session=session,
                    bot=bot,
                    task=task,
                    role="copywriter",
                    user_telegram_id=task.copywriter_id,
                    flag_attr="copy_reminder_sent",
                    message_text=(
                        "⏰ <b>Eslatma!</b>\n"
                        f"📌 Vazifa: <b>{task.task_name}</b>\n"
                        "Deadline 1 kun qoldi. Matnni topshirishni unutmang."
                    ),
                )

            # Marketer reminder
            if task.marketer_id:
                await _send_role_reminder_if_needed(
                    session=session,
                    bot=bot,
                    task=task,
                    role="marketer",
                    user_telegram_id=task.marketer_id,
                    flag_attr="market_reminder_sent",
                    message_text=(
                        "⏰ <b>Eslatma!</b>\n"
                        f"📌 Vazifa: <b>{task.task_name}</b>\n"
                        "Deadline 1 kun qoldi. Postni nashr qilib linkni yuboring."
                    ),
                )

        await session.commit()


async def _send_role_reminder_if_needed(
    session,
    bot,
    task: Task,
    role: str,
    user_telegram_id: int,
    flag_attr: str,
    message_text: str,
):
    """
    Flag bo'lsa bir marta yuboradi.
    Flag bo'lmasa ham yuboradi, lekin spam bo'lishi mumkin (log beradi).
    """
    if not user_telegram_id:
        return

    has_flag = hasattr(task, flag_attr)
    already_sent = getattr(task, flag_attr, False) if has_flag else False

    if has_flag and already_sent:
        return

    try:
        await bot.send_message(
            user_telegram_id,
            message_text,
            parse_mode="HTML",
        )
        if has_flag:
            setattr(task, flag_attr, True)
        else:
            logger.warning(
                f"Task.id={task.id} reminder flag '{flag_attr}' yo'q. "
                f"Bu spam bo'lishi mumkin. models.py + migration qo'shing."
            )
    except Exception as e:
        logger.error(f"Reminder send failed role={role} user_id={user_telegram_id}: {e}")


# =========================================================
# JOB 2: Auto month rollover (har oy 25-kun)
# =========================================================
async def job_auto_open_new_month(bot):
    """
    Har oy 25-kun:
    - Month template tab -> yangi oy tab
    - Har xodim uchun employee template -> "FullName NewMonth"
    - DB worksheet_name update
    - (ixtiyoriy) adminlarga xabar
    """
    sheet_id = settings.DEFAULT_SPREADSHEET_ID
    now = datetime.now()
    new_month = sheets_service.get_next_month_name(now)

    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.full_name))).scalars().all()
        employee_full_names = [u.full_name for u in users if u.full_name]

    if not employee_full_names:
        logger.info("Auto month: userlar yo'q, skip.")
        return

    try:
        await sheets_service.create_month_and_employee_tabs(
            sheet_id=sheet_id,
            new_month=new_month,
            employee_full_names=employee_full_names,
        )
    except Exception as e:
        logger.error(f"Auto month open error: {e}")
        return

    # DB update
    async with async_session() as session:
        users = (await session.execute(select(User))).scalars().all()
        for u in users:
            if not u.full_name:
                continue
            u.personal_sheet_id = sheet_id
            u.worksheet_name = f"{u.full_name} {new_month}"
        await session.commit()

    # Adminlarga xabar (xohlasangiz)
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📅 <b>Yangi oy avtomatik ochildi:</b> <b>{new_month}</b>\n"
                "Barcha xodimlar uchun tablar yaratildi va DB yangilandi.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Admin notify (month open) failed admin_id={admin_id}: {e}")


# =========================================================
# Setup
# =========================================================
def setup_scheduler(bot):
    """
    main.py dan:
        from src.services.scheduler import setup_scheduler
        setup_scheduler(bot)
    """
    scheduler = AsyncIOScheduler(timezone=_get_timezone())

    # Deadline reminders: har 10 daqiqada tekshiradi (yengil)
    scheduler.add_job(
        job_deadline_reminders,
        trigger=CronTrigger(minute="*/10"),
        args=[bot],
        id="deadline_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Auto month rollover (agar yoqilgan bo'lsa)
    auto_rollover = str(getattr(settings, "AUTO_MONTH_ROLLOVER", "true")).lower() in ("1", "true", "yes", "on")
    if auto_rollover:
        day = int(getattr(settings, "AUTO_MONTH_DAY", 25))
        hour = int(getattr(settings, "AUTO_MONTH_HOUR", 9))
        minute = int(getattr(settings, "AUTO_MONTH_MINUTE", 0))

        scheduler.add_job(
            job_auto_open_new_month,
            trigger=CronTrigger(day=day, hour=hour, minute=minute),
            args=[bot],
            id="auto_month_rollover",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info(f"📅 Auto month rollover ON: har oy {day}-kuni {hour:02d}:{minute:02d}")

    else:
        logger.info("📅 Auto month rollover OFF")

    scheduler.start()
    logger.info("⏰ Scheduler ishga tushdi.")
    return scheduler