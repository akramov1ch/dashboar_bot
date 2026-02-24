import logging
from datetime import datetime
from typing import List, Optional, Tuple

import gspread_asyncio
from google.oauth2.service_account import Credentials

from src.config import settings

logger = logging.getLogger(__name__)


# =========================================================
# 📅 OY NOMLARI (UZ)
# =========================================================

MONTHS_UZ = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"
]


def normalize_month(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    return s[0].upper() + s[1:].lower()


def get_next_month_name(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    idx = now.month - 1
    next_idx = (idx + 1) % 12
    return MONTHS_UZ[next_idx]


def is_month_name(s: str) -> bool:
    return normalize_month(s) in MONTHS_UZ


def replace_last_month_token(full: str, new_month: str) -> str:
    full = (full or "").strip()
    new_month = normalize_month(new_month)

    if not full:
        return new_month

    parts = full.split()
    if parts and is_month_name(parts[-1]):
        parts[-1] = new_month
        return " ".join(parts)

    return f"{full} {new_month}"


# =========================================================
# 📊 GOOGLE SHEETS SERVICE
# =========================================================

class GoogleSheetsService:

    def __init__(self):
        self.client_manager = gspread_asyncio.AsyncioGspreadClientManager(
            self._get_scoped_credentials
        )

    def _get_scoped_credentials(self):
        creds = Credentials.from_service_account_file(
            settings.GOOGLE_SHEET_JSON_PATH
        )
        return creds.with_scopes([
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])

    async def _open_spreadsheet(self, sheet_id: str):
        gc = await self.client_manager.authorize()
        return await gc.open_by_key(sheet_id)

    async def _get_worksheet(self, sheet_id: str, worksheet_name: str):
        spreadsheet = await self._open_spreadsheet(sheet_id)
        return await spreadsheet.worksheet(worksheet_name.strip())

    # =========================================================
    # 🔎 WORKSHEET UTILS
    # =========================================================

    async def worksheet_exists(self, sheet_id: str, worksheet_name: str) -> bool:
        try:
            await self._get_worksheet(sheet_id, worksheet_name)
            return True
        except Exception:
            return False

    async def duplicate_worksheet(self, sheet_id: str, source_tab: str, new_tab: str):
        spreadsheet = await self._open_spreadsheet(sheet_id)

        # agar mavjud bo‘lsa skip
        try:
            await spreadsheet.worksheet(new_tab)
            logger.info(f"Tab mavjud: {new_tab}")
            return
        except Exception:
            pass

        src_ws = await spreadsheet.worksheet(source_tab)
        await src_ws.duplicate(new_sheet_name=new_tab)
        logger.info(f"Duplicated: {source_tab} -> {new_tab}")

    async def update_cell_safe(self, sheet_id: str, tab: str, row: int, col: int, value: str):
        try:
            ws = await self._get_worksheet(sheet_id, tab)
            await ws.update_cell(row, col, value)
        except Exception as e:
            logger.error(f"update_cell_safe error: {e}")

    async def bulk_update_column_values(
        self,
        sheet_id: str,
        tab: str,
        col_index: int,
        start_row: int,
        values: List[str]
    ):
        if not values:
            return

        ws = await self._get_worksheet(sheet_id, tab)
        end_row = start_row + len(values) - 1
        col_letter = chr(ord("A") + col_index - 1)
        rng = f"{col_letter}{start_row}:{col_letter}{end_row}"

        await ws.update(rng, [[v] for v in values])

    # =========================================================
    # 📝 VAZIFA FUNKSIYALARI
    # =========================================================

    async def add_task_to_sheet(
        self,
        sheet_id: str,
        worksheet_name: str,
        task_name: str,
        deadline: str,
        priority: str
    ) -> int:

        worksheet = await self._get_worksheet(sheet_id, worksheet_name)

        col_b_values = await worksheet.col_values(2)

        next_row = 8
        found = False

        for i in range(7, 77):
            if i >= len(col_b_values) or not col_b_values[i].strip():
                next_row = i + 1
                found = True
                break

        if not found:
            raise ValueError("Bo'sh joy qolmadi (8-77)")

        await worksheet.update_cell(next_row, 2, task_name)
        await worksheet.update_cell(next_row, 3, "Jarayonda")
        await worksheet.update_cell(next_row, 5, deadline)
        await worksheet.update_cell(next_row, 20, priority)
        await worksheet.update_cell(next_row, 29, "Yangi topshiriq ⚪")

        return next_row

    async def update_progress_status(
        self,
        sheet_id: str,
        worksheet_name: str,
        row_index: int,
        holati_text: str,
        status_text: Optional[str] = None
    ):
        worksheet = await self._get_worksheet(sheet_id, worksheet_name)

        await worksheet.update_cell(row_index, 13, holati_text)
        if status_text:
            await worksheet.update_cell(row_index, 29, status_text)

    async def write_final_link(
        self,
        sheet_id: str,
        worksheet_name: str,
        row_index: int,
        link: str
    ):
        worksheet = await self._get_worksheet(sheet_id, worksheet_name)
        await worksheet.update_cell(row_index, 34, link)

    async def write_director_comment(
        self,
        sheet_id: str,
        worksheet_name: str,
        row_index: int,
        comment: str
    ):
        worksheet = await self._get_worksheet(sheet_id, worksheet_name)
        await worksheet.update_cell(row_index, 35, comment)

    # =========================================================
    # 🚀 AVTOMATIK OY YARATISH
    # =========================================================

    async def create_month_and_employee_tabs(
        self,
        sheet_id: str,
        new_month: str,
        employee_full_names: List[str]
    ) -> Tuple[str, List[str]]:

        new_month = normalize_month(new_month)

        # 1️⃣ OY TAB
        await self.duplicate_worksheet(
            sheet_id,
            settings.MONTH_TEMPLATE_TAB,
            new_month
        )

        employee_tabs = []

        # 2️⃣ XODIM TABLAR
        for full_name in employee_full_names:
            tab_name = replace_last_month_token(full_name, new_month)

            await self.duplicate_worksheet(
                sheet_id,
                settings.EMPLOYEE_TEMPLATE_TAB,
                tab_name
            )

            employee_tabs.append(tab_name)

            # Xodim tab A1 ga oy yozish
            await self.update_cell_safe(sheet_id, tab_name, 1, 1, new_month)

        # 3️⃣ Oy jadvalidagi ism-familiyalarni yangilash
        try:
            ws = await self._get_worksheet(sheet_id, new_month)
            col_a = await ws.col_values(1)

            updated_values = []
            start_row = 3

            for i in range(start_row - 1, len(col_a)):
                v = (col_a[i] or "").strip()
                if not v:
                    break
                updated_values.append(
                    replace_last_month_token(v, new_month)
                )

            if updated_values:
                await self.bulk_update_column_values(
                    sheet_id,
                    new_month,
                    col_index=1,
                    start_row=3,
                    values=updated_values
                )
        except Exception as e:
            logger.error(f"Oy jadval update error: {e}")

        return new_month, employee_tabs


# Global instance
sheets_service = GoogleSheetsService()