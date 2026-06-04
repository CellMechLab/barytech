"""Application settings loaded from environment variables and backend/new_architecture/.env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolves .env next to run.py so uvicorn cwd does not affect loading
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # JWT configuration
    SECRET_KEY: str = "your_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database configuration
    DATABASE_URL: str = "sqlite:///./test.db"

    # Raspberry Pi printer_control_service (WebSocket + REST)
    PRINTER_HOST: str = "10.99.134.9"
    PRINTER_PORT: int = 8001
    PRINTER_WS_URL: str = "ws://10.99.134.9:8001/ws"
    PRINTER_API_URL: str = "http://10.99.134.9:8001"

    # MQTT broker (mosquitto on Pi or local)
    MQTT_HOST: str = "10.99.134.9"
    MQTT_PORT: int = 1883
    MQTT_KEEPALIVE: int = 60

    DEBUG: bool = True

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
