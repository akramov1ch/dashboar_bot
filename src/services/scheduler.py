import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

def setup_scheduler():
    """
    Hozircha avtomatik vazifalar o'chirildi. 
    Siz dashboardlarni qo'lda biriktirasiz.
    """
    scheduler = AsyncIOScheduler()
    # Hech qanday job qo'shilmaydi
    scheduler.start()
    logger.info("⏰ Scheduler bo'sh rejimda ishga tushdi.")