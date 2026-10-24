"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid float for environment variable {key}: {raw!r}") from exc


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for environment variable {key}: {raw!r}") from exc


class Settings:
    """Typed configuration loaded on first access."""

    def __init__(self) -> None:
        self.celesto_provider: str = _env_str("CELESTO_PROVIDER", "cloud")
        self.celesto_api_key: str = _env_str("CELESTO_API_KEY", "")
        self.celesto_backend: str = _env_str("CELESTO_BACKEND", "firecracker")
        self.celesto_template_id: str = _env_str("CELESTO_TEMPLATE_ID", "coding-agent")
        self.celesto_no_telemetry: int = _env_int("CELESTO_NO_TELEMETRY", 1)

        self.llm_base_url: str = _env_str("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.llm_api_key: str = _env_str("LLM_API_KEY", "")
        self.llm_model: str = _env_str("LLM_MODEL", "llama-3.3-70b-versatile")
        self.llm_min_interval_s: float = _env_float("LLM_MIN_INTERVAL_S", 0.0)

        self.database_url: str = _env_str(
            "DATABASE_URL", "postgresql://ledger:ledger@ledger:5432/ledger"
        )
        self.harness_database_url: str = _env_str(
            "HARNESS_DATABASE_URL", "postgresql://ledger:ledger@localhost:5433/ledger"
        )
        self.ledger_port: int = _env_int("LEDGER_PORT", 5433)
        self.api_port: int = _env_int("API_PORT", 8080)

        self.sandbox_size: str = _env_str("SANDBOX_SIZE", "micro")
        self.sandbox_price_per_hour_usd: float = _env_float("SANDBOX_PRICE_PER_HOUR_USD", 0.015)
        self.llm_input_price_per_mtok_usd: float = _env_float("LLM_INPUT_PRICE_PER_MTOK_USD", 0.0)
        self.llm_output_price_per_mtok_usd: float = _env_float("LLM_OUTPUT_PRICE_PER_MTOK_USD", 0.0)

        self.agent_max_turns: int = _env_int("AGENT_MAX_TURNS", 14)
        self.run_timeout_s: int = _env_int("RUN_TIMEOUT_S", 600)
        self.step_timeout_s: int = _env_int("STEP_TIMEOUT_S", 120)

        self.log_level: str = _env_str("LOG_LEVEL", "INFO")
        self.reports_dir: Path = Path(_env_str("REPORTS_DIR", "reports"))
        self.logs_dir: Path = Path(_env_str("LOGS_DIR", "logs"))
        self.audit_log_path: Path = Path(_env_str("AUDIT_LOG_PATH", "logs/commands.jsonl"))
        self.committed_commands_log: Path = Path(
            _env_str("COMMITTED_COMMANDS_LOG", "logs/commands.jsonl")
        )
        self.evidence_dir: Path = Path(_env_str("EVIDENCE_DIR", "reports/evidence"))
        self.readme_path: Path = Path(_env_str("README_PATH", "README.md"))
        self.fixtures_dir: Path = Path(_env_str("FIXTURES_DIR", "fixtures/cases"))


settings = Settings()
