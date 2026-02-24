# src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Union, Optional

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: Union[str, List[int]]
    DATABASE_URL: str
    GOOGLE_SHEET_JSON_PATH: str
    DEFAULT_SPREADSHEET_ID: str
    GROUP_ID: int

    # ✅ NEW: auto month rollover settings
    TIMEZONE: str = "Asia/Tashkent"
    AUTO_MONTH_ROLLOVER: bool = True
    AUTO_MONTH_DAY: int = 25
    AUTO_MONTH_HOUR: int = 9
    AUTO_MONTH_MINUTE: int = 0

    # ✅ NEW: template tab names in Google Sheets
    MONTH_TEMPLATE_TAB: str = "__OY_SHABLON__"
    EMPLOYEE_TEMPLATE_TAB: str = "__XODIM_SHABLON__"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",")]
        elif isinstance(v, int):
            return [v]
        return v

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()