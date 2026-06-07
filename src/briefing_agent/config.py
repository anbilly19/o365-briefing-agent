"""Centralised settings — all env vars read here, nowhere else."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Microsoft Graph
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""
    user_email: str = ""

    # Local LLM
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "gemma3:4b"

    # Pipeline
    lookback_hours: int = 24
    batch_size: int = 5          # messages per LLM batch (keep small for local models)
    num_predict: int = 2048      # max output tokens per batch
    num_ctx: int = 8192          # context window per batch

    # Output
    output_dir: Path = Path("output")


settings = Settings()
