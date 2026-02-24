import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from src.config import settings
from src.database.base import init_db
from src.services.scheduler import setup_scheduler
from src.bot.handlers import common, admin, content_maker, production


async def main():
    # Logging sozlamalari
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    # 1) DB init
    await init_db()

    # 2) Bot
    bot = Bot(
        token=settings.BOT_TOKEN,
        parse_mode=ParseMode.HTML
    )

    # 3) Scheduler (bot bilan!)
    setup_scheduler(bot)

    # 4) Dispatcher
    dp = Dispatcher()

    # 5) Routers
    dp.include_routers(
        common.router,
        admin.router,
        content_maker.router,
        production.router
    )

    logging.info("🚀 Bot marketing production tizimida ishga tushdi!")

    try:
        # polling conflict bo'lmasligi uchun webhookni o'chirib qo'yamiz
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Bot ishlashida xatolik yuz berdi: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi!")