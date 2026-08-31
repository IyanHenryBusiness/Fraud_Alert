from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_NAME: str = "Fraud Investigation API"
    APP_VERSION: str = "1.0.0"

    COPILOT_MODE: str = "mock"
    COPILOT_TOKEN_ENDPOINT: str = ""
    COPILOT_DIRECT_LINE_BASE_URL: str = (
        "https://directline.botframework.com/v3/directline"
    )
    COPILOT_RESPONSE_TIMEOUT_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()


