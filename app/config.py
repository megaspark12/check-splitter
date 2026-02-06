"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    app_name: str = "Receipt Splitter"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./receipt_splitter.db"
    
    # AI Vision (Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-preview-05-20"  # Latest vision model
    
    # Session
    session_expiry_minutes: int = 15
    session_code_length: int = 6
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
