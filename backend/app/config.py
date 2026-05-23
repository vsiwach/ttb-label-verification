"""Runtime configuration loaded from environment / .env."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    inference_mode: Literal["mock", "cloud", "claude-code", "onprem", "sft"] = "mock"

    # Comma-separated origins; parsed in main.py
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Cloud adapter (not exercised in mock mode)
    cloud_provider: Literal["anthropic", "openai", "google"] = "anthropic"
    cloud_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # On-prem adapter (not exercised in mock mode)
    onprem_vlm_url: str = "http://localhost:11434"
    onprem_vlm_model: str = "phi3.5"

    # SFT adapter (used when inference_mode=sft). Points at a bundle that
    # contains a manifest.json (Qwen LoRA or Donut full fine-tune).
    sft_model_dir: str = "backend/models/qwen2_5_vl_7b"


settings = Settings()
