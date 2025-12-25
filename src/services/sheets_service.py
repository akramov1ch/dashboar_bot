import asyncio
import gspread_asyncio
from google.oauth2.service_account import Credentials
from src.config import settings
import logging

logger = logging.getLogger(__name__)

class GoogleSheetsService:
    def __init__(self):
        self.client_manager = gspread_asyncio.AsyncioGspreadClientManager(self._get_scoped_credentials)

    def _get_scoped_credentials(self):
        creds = Credentials.from_service_account_file(settings.GOOGLE_SHEET_JSON_PATH)
        return creds.with_scopes([
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])

    async def _get_worksheet(self, sheet_id: str, worksheet_name: str):
        gc = await self.client_manager.authorize()
        spreadsheet = await gc.open_by_key(sheet_id)
        try:
            return await spreadsheet.worksheet(worksheet_name.strip())
        except Exception as e:
            logger.error(f"Worksheet '{worksheet_name}' topilmadi: {e}")
            raise ValueError(f"Varaq topilmadi: {worksheet_name}")

    async def add_task_to_sheet(self, sheet_id: str, worksheet_name: str, task_name: str, deadline: str, priority: str) -> int:
        """Vazifani aniq kataklarga yozish (Merged cell'larni buzmaslik uchun)"""
        try:
            worksheet = await self._get_worksheet(sheet_id, worksheet_name)
            col_b_values = await worksheet.col_values(2) 
            next_row = len(col_b_values) + 1
            if next_row < 8: next_row = 8

            # Har bir katakni alohida yangilaymiz
            await worksheet.update_cell(next_row, 2, task_name)      # B: Vazifa nomi
            await worksheet.update_cell(next_row, 3, "1")            # C: Natijasi
            await worksheet.update_cell(next_row, 5, deadline)       # G: Yakunlanish sanasi (7-ustun) ✅
            await worksheet.update_cell(next_row, 20, priority)      # T: Muhimlik darajasi (20-ustun)
            await worksheet.update_cell(next_row, 29, "Yangi topshiriq ⚪") # AC: Status (29-ustun)

            return next_row
        except Exception as e:
            logger.error(f"Sheets add_task error: {e}")
            raise

    async def update_task_columns(self, sheet_id: str, worksheet_name: str, row_index: int, holati: str = None, status: str = None):
        """M (13) va AC (29) ustunlarini yangilash"""
        try:
            worksheet = await self._get_worksheet(sheet_id, worksheet_name)
            if holati:
                await worksheet.update_cell(row_index, 13, holati) # M ustuni
            if status:
                await worksheet.update_cell(row_index, 29, status) # AC ustuni
        except Exception as e:
            logger.error(f"Sheets update error: {e}")

    async def update_direktor_feedback(self, sheet_id: str, worksheet_name: str, row_index: int, text: str):
        """AL (38) ustuniga direktor izohini yozish"""
        try:
            worksheet = await self._get_worksheet(sheet_id, worksheet_name)
            await worksheet.update_cell(row_index, 38, text) # AL ustuni
        except Exception as e:
            logger.error(f"Direktor feedback error: {e}")

    async def get_all_rows(self, sheet_id: str, worksheet_name: str):
        try:
            worksheet = await self._get_worksheet(sheet_id, worksheet_name)
            return await worksheet.get_all_values()
        except: return []

sheets_service = GoogleSheetsService()