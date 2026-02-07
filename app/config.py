"""Application configuration."""
import sys
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    app_name: str = "Check Splitter"
    version: str = "1.0.0"
    debug: bool = False  # Default to False for production safety
    secret_key: str = "dev-secret-key-change-in-production"
    environment: str = "development"  # development, staging, production
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    metrics_port: int = 9090  # Internal metrics port
    workers: int = 1
    
    # CORS - comma-separated list of allowed origins
    cors_origins: str = "*"
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./check_splitter.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_echo: bool = False  # Log SQL queries
    
    # AI Vision (Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-preview-05-20"  # Latest vision model
    
    # Session
    session_expiry_minutes: int = 15
    session_code_length: int = 6
    
    # File uploads
    max_upload_size_mb: int = 10
    uploads_dir: str = "uploads"
    
    # Rate limiting
    rate_limit_per_minute: int = 180
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def max_upload_size_bytes(self) -> int:
        """Get max upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024
    
    def validate_production_config(self) -> None:
        """Validate that production-required settings are configured."""
        if self.is_production:
            errors = []
            
            if self.secret_key == "dev-secret-key-change-in-production":
                errors.append("SECRET_KEY must be set in production")
            
            if self.debug:
                errors.append("DEBUG must be False in production")
            
            if self.cors_origins == "*":
                errors.append("CORS_ORIGINS should not be '*' in production")
            
            if "sqlite" in self.database_url.lower():
                # Warning only, not an error
                print("WARNING: Using SQLite in production is not recommended", file=sys.stderr)
            
            if errors:
                raise ValueError(
                    "Production configuration errors:\n" + 
                    "\n".join(f"  - {e}" for e in errors)
                )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.validate_production_config()
    return settings
