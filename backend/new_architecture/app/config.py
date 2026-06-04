from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # JWT configuration
    SECRET_KEY: str = "your_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database configuration
    DATABASE_URL: str = "sqlite:///./test.db"

    PRINTER_WS_URL: str = "ws://10.99.134.8:8003/ws"
    PRINTER_API_URL: str = "http://10.99.134.8:8003"

    DEBUG: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"    # ← add this

settings = Settings()