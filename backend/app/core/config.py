from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Research Workspace"
    api_prefix: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = "sqlite:///./research_workspace.db"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "change-this-secret-before-deploy"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24 * 7
    app_username: str = "admin"
    app_password: str = "change-me"
    knowledge_base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[3] / "knowledge_base")
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    dashscope_api_key: str = ""
    qwen_embedding_model: str = "text-embedding-v4"
    pdf_parser: str = "auto"
    mineru_api_base: str = ""
    mineru_api_token: str = ""
    mineru_language: str = "ch"
    mineru_enable_table: bool = True
    mineru_enable_formula: bool = True
    mineru_is_ocr: bool = False
    mineru_timeout: int = 300
    mineru_poll_interval: float = 3.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
