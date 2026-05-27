"""Runtime configuration loaded from environment / .env."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Default is "modal" — production path routes to the Qwen2.5-VL v2 LoRA
    # endpoint on Modal (privacy-first, on-prem-equivalent). Local dev can
    # override to "cloud" (Haiku/Sonnet via Anthropic API) or "mock" for
    # offline/test work. The deploy URL is configured via MODAL_ENDPOINT_URL.
    inference_mode: Literal["mock", "cloud", "claude-code", "onprem", "sft", "modal"] = "modal"

    # Comma-separated origins; parsed in main.py
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Cloud adapter (not exercised in mock mode)
    cloud_provider: Literal["anthropic", "openai", "google"] = "anthropic"
    cloud_model: str = "claude-sonnet-4-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # On-prem adapter (not exercised in mock mode)
    onprem_vlm_url: str = "http://localhost:11434"
    onprem_vlm_model: str = "phi3.5"

    # SFT adapter (used when inference_mode=sft). Points at a bundle that
    # contains a manifest.json (Qwen LoRA or Donut full fine-tune).
    sft_model_dir: str = "backend/models/qwen2_5_vl_7b"

    # Modal-hosted Qwen endpoint (used when inference_mode=modal). Default
    # points at the deployed v2 endpoint; override via env for staging URLs.
    modal_endpoint_url: str = "https://vsiwach--ttb-qwen-extractor-v2-extract-web.modal.run"
    # Companion warm-check endpoint. Same Modal app, different function —
    # health_web instead of extract_web. /api/health pings this with a
    # 5s budget; warm round-trips are sub-second, a timeout signals the
    # GPU container is still cold-starting (load_model runs ~30-60s).
    modal_health_url:   str = "https://vsiwach--ttb-qwen-extractor-v2-health-web.modal.run"
    # Separate CPU-only Modal endpoint for Tesseract OCR — provides the
    # DETERMINISTIC warning bbox + EXIF DPI used by the 27 CFR 16.22
    # type-size check. Vercel calls it in parallel with the Qwen + Haiku
    # calls so warm-path latency stays at the slower-of-three (Qwen ~5s).
    # Empty string disables the Tesseract path and the engine falls back
    # to Haiku's (non-deterministic) bbox.
    modal_tesseract_url: str = "https://vsiwach--ttb-tesseract-tesseract-web.modal.run"
    # Budget for the Modal extract call. When exceeded, ModalRemoteExtractor
    # falls back to the Haiku result (already running in parallel) so the
    # user gets a sub-10s answer instead of waiting through Modal's cold
    # start. Warm Modal calls return in ~5-7s so 8s gives a small safety
    # margin while still meeting the under-9s end-to-end target.
    modal_timeout: float = 8.0
    # Budget for the warm-check probe. Must stay well under Vercel's
    # 30s function maxDuration so /api/health itself never times out.
    modal_health_timeout: float = 5.0


settings = Settings()
