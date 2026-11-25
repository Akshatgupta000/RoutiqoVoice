"""Application settings.

Everything sensitive or environment-specific comes from environment variables.
The Gemini model name is not hard-coded in the rest of the app so it can be
changed when Google retires a model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
KNOWLEDGE_PATH = PROJECT_ROOT / "knowledge" / "routiqo_knowledge.md"

# Values from .env.example that mean "the user has not configured this yet".
_KEY_PLACEHOLDERS = {"", "your_api_key_here", "changeme"}
_MODEL_PLACEHOLDERS = {"", "your_model_name_here"}


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    database_path: str
    config_issue: str | None

    @property
    def ai_configured(self) -> bool:
        """True only when both a real key and a real model name are present."""
        return not self.config_issue

    def __repr__(self) -> str:
        # Never include the API key in logs or debug output.
        return (
            "Settings("
            f"ai_configured={self.ai_configured}, "
            f"model={self.gemini_model!r}, "
            f"database_path={self.database_path!r})"
        )


def _resolve_database_path(raw: str) -> str:
    path = Path(raw.strip() or "./routiqo_sales.db")
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


@lru_cache
def get_settings() -> Settings:
    """Load settings once. Tests call get_settings.cache_clear() after changing env."""
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "").strip()
    database_path = _resolve_database_path(os.getenv("DATABASE_PATH", "./routiqo_sales.db"))

    usable_key = "" if api_key.lower() in _KEY_PLACEHOLDERS else api_key
    usable_model = "" if model.lower() in _MODEL_PLACEHOLDERS else model

    config_issue = None
    if not usable_key and not usable_model:
        config_issue = "GEMINI_API_KEY is not set. The app is running in demo mode."
    elif not usable_key:
        config_issue = "GEMINI_API_KEY is not set. The app is running in demo mode."
    elif not usable_model:
        config_issue = "Set GEMINI_MODEL in .env to a current Gemini model id."

    return Settings(
        gemini_api_key=usable_key,
        gemini_model=usable_model,
        database_path=database_path,
        config_issue=config_issue,
    )
