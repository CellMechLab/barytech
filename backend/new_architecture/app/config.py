from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # JWT configuration
    SECRET_KEY: str = "your_secret_key"  # Replace with a strong secret key
    ALGORITHM: str = "HS256"  # Algorithm used for JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # Token expiry time in minutes

    # Database configuration
    DATABASE_URL: str = "sqlite:///./test.db"  # Update to your actual database URL

    # Stores the printer WebSocket endpoint used by printer_router to talk to the Pi service.
    PRINTER_WS_URL: str = "ws://10.99.134.8:8003/ws"

    # Stores the printer HTTP API base URL used by backend routes that proxy printer commands.
    PRINTER_API_URL: str = "http://10.99.134.8:8003"

    # Additional settings can go here
    DEBUG: bool = True

    class Config:
        env_file = ".env"  # Load environment variables from a .env file if available

# Instantiate the settings object
settings = Settings()
