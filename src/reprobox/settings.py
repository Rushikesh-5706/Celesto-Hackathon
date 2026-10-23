"""Application settings loaded from environment variables.

Every field has a default so the API container stays healthy with no .env file.
Secrets carry no default and stay empty strings; the provider factory handles
the missing-key case at call time, not at import time.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    """Typed, lazily-evaluated view of the process environment."""

    # --- Secrets (no defaults; empty string means "not configured") ---
    celesto_api_key: str = _env("CELESTO_API_KEY")
    llm_api_key: str = _env("LLM_API_KEY")

    # --- LLM ---
    llm_base_url: str = _env("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_model: str = _env("LLM_MODEL", "llama-3.3-70b-versatile")

    # --- Provider ---
    celesto_provider: str = _env("CELESTO_PROVIDER", "cloud")
    celesto_template_id: str = _env("CELESTO_TEMPLATE_ID", "coding-agent")

    # --- Sandbox ---
    sandbox_size: str = _env("SANDBOX_SIZE", "micro")
    sandbox_price_per_hour_usd: float = _env_float("SANDBOX_PRICE_PER_HOUR_USD", 0.015)

    # --- LLM pricing (for cost accounting) ---
    llm_input_price_per_mtok_usd: float = _env_float("LLM_INPUT_PRICE_PER_MTOK_USD", 0.0)
    llm_output_price_per_mtok_usd: float = _env_float("LLM_OUTPUT_PRICE_PER_MTOK_USD", 0.0)

    # --- Agent ---
    agent_max_turns: int = _env_int("AGENT_MAX_TURNS", 14)
    run_timeout_s: int = _env_int("RUN_TIMEOUT_S", 600)
    step_timeout_s: int = _env_int("STEP_TIMEOUT_S", 120)

    # --- Logging and paths ---
    log_level: str = _env("LOG_LEVEL", "INFO")
    reports_dir: Path = Path(_env("REPORTS_DIR", "reports"))
    logs_dir: Path = Path(_env("LOGS_DIR", "logs"))
    audit_log_path: Path = Path(_env("AUDIT_LOG_PATH", "logs/commands.jsonl"))
    fixtures_dir: Path = Path(_env("FIXTURES_DIR", "fixtures/cases"))

    # --- Database ---
    database_url: str = _env("DATABASE_URL", "postgresql://ledger:ledger@localhost:5433/ledger")
    ledger_port: int = _env_int("LEDGER_PORT", 5433)

    # --- API server ---
    api_port: int = _env_int("API_PORT", 8080)


# Module-level singleton — imported everywhere as `from reprobox.settings import settings`.
settings = Settings()
