from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    ADMIN_IDS_STR: str = Field(default="", alias="ADMIN_ID")
    ADMIN_IDS: list[int] = []

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v, info):
        raw = info.data.get("ADMIN_IDS_STR", "")
        if not raw:
            return []
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]

    MAIN_GROUP_ID: int
    THREAD_SALES: int
    THREAD_ASSORTMENT: int
    THREAD_ARRIVAL: int
    THREAD_PREORDER: int
    THREAD_SERVICE: int = 0

    DATABASE_URL: str
    RENDER_URL: str = Field(default="", alias="RENDER_EXTERNAL_URL")
    PORT: int = 8000
    PLAN_AMOUNT: int = 600000

    ADMIN_PASSWORD: str = ""
    ADMIN_PASSWORD_HASH: str = ""
    SECRET_KEY: str = ""

    REDIS_URL: str = ""

    @model_validator(mode="after")
    def validate_secrets(self):
        if not self.SECRET_KEY or len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY должен содержать не менее 32 символов")
        if not self.ADMIN_PASSWORD and not self.ADMIN_PASSWORD_HASH:
            raise ValueError("Должен быть задан ADMIN_PASSWORD или ADMIN_PASSWORD_HASH")
        return self


config = Settings()

# Aliases for compatibility with bot/__init__.py
get_settings = lambda: config
settings = config
