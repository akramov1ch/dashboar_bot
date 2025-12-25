from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Union

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: Union[str, List[int]] 
    DATABASE_URL: str
    GOOGLE_SHEET_JSON_PATH: str
    # Asosiy Google Sheet faylining ID-si (Linkdagi /d/ dan keyingi qism)
    DEFAULT_SPREADSHEET_ID: str 

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