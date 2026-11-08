from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from pydantic import SecretStr


class Settings(BaseSettings):

    llm_provider: str 
    llm_model: str
    llm_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/loan_underwriting.db"

    upload_dir: Path = Path("data/uploads")
    max_upload_size_mb: int = 10
    
    
settings = Settings()