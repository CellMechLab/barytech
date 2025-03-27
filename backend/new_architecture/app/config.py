from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # JWT configuration
    SECRET_KEY: str = "your_secret_key"  # Replace with a strong secret key
    ALGORITHM: str = "HS256"  # Algorithm used for JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # Token expiry time in minutes

    # Database configuration
    DATABASE_URL: str = "sqlite:///./test.db"  # Update to your actual database URL

    # Additional settings can go here
    DEBUG: bool = True

    class Config:
        env_file = ".env"  # Load environment variables from a .env file if available

# Instantiate the settings object
settings = Settings()
