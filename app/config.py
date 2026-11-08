from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path



class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/loan_underwriting.db"

    upload_dir: Path = Path("data/uploads")
    max_upload_size_mb: int = 10
    
    
settings = Settings()