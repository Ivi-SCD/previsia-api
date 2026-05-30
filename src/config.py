from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    supabase_url: str = ""
    supabase_key: str = ""
    groq_api_key: str = ""

    jwt_secret: str = "change-me-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_expires_min: int = 60

    model_dir: Path = Path("models")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
