from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from pydantic import SecretStr

llm_provider: str = "google-genai"
llm_model: str = "gemini-3.8-flash"
llm_api_key: SecretStr | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/loan_underwriting.db"

    upload_dir: Path = Path("data/uploads")
    max_upload_size_mb: int = 10
    
    
settings = Settings()