from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_host: str = os.getenv("AGNO_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("AGNO_API_PORT", "8001"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    pocketbase_url: str = os.getenv("POCKETBASE_URL", "")
    pocketbase_admin_token: str = os.getenv("POCKETBASE_ADMIN_TOKEN", "")
    storage_dir: str = os.getenv("APP_STORAGE_DIR", ".tmp/agno-api")


settings = Settings()
