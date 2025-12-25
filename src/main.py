import asyncio
import logging
from aiogram import Bot, Dispatcher
from src.config import settings
from src.database.base import init_db
from src.services.scheduler import setup_scheduler
from src.bot.handlers import common, admin, employee

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # 1. Bazani yaratish
    await init_db()

    # 2. Scheduler (Hozircha bo'sh)
    setup_scheduler()

    # 3. Botni yoqish
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    
    # Handlerlarni ulash
    dp.include_routers(
        common.router, 
        admin.router, 
        employee.router
    )

    logging.info("🚀 Bot xodimlar dashboardi tizimida ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())