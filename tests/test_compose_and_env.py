"""Tests validating docker-compose.yml structure, healthchecks, and .env.example parity."""

from pathlib import Path

import yaml

from reprobox.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

REQUIRED_BLOCK = """CELESTO_PROVIDER=cloud
CELESTO_API_KEY=replace-me
CELESTO_BACKEND=firecracker
LLM_BASE_URL=https://example-llm-host/v1
LLM_API_KEY=replace-me
LLM_MODEL=replace-with-a-model-name
DATABASE_URL=postgresql://ledger:ledger@ledger:5432/ledger
API_PORT=8080"""


def test_compose_yaml_structure_and_healthchecks():
    assert COMPOSE_FILE.exists(), "docker-compose.yml is missing"
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    assert "services" in data, "compose must define services"
    services = data["services"]
    assert (
        "api" in services and "ledger" in services
    ), "compose must contain api and ledger services"

    # Ledger checks
    ledger = services["ledger"]
    assert "healthcheck" in ledger
    l_hc = ledger["healthcheck"]
    for field in ("interval", "timeout", "retries", "start_period"):
        assert field in l_hc, f"ledger healthcheck missing {field}"
    assert any("pg_isready" in str(cmd) for cmd in l_hc.get("test", []))
    assert any("./seeds:" in str(v) for v in ledger.get("volumes", []))

    # API checks
    api = services["api"]
    assert "healthcheck" in api
    a_hc = api["healthcheck"]
    for field in ("interval", "timeout", "retries", "start_period"):
        assert field in a_hc, f"api healthcheck missing {field}"
    assert any("8080/health" in str(cmd) for cmd in a_hc.get("test", []))

    # Dependency check
    deps = api.get("depends_on", {})
    assert "ledger" in deps
    assert deps["ledger"].get("condition") == "service_healthy"

    # Runtime logs and audit paths under /app/var
    api_env = api.get("environment", {})
    assert api_env.get("LOGS_DIR") == "/app/var"
    assert api_env.get("AUDIT_LOG_PATH") == "/app/var/commands.jsonl"
    assert api_env.get("EVIDENCE_DIR") == "/app/var/evidence"

    # No bind mount of reports or logs in api
    for vol in api.get("volumes", []):
        v_str = str(vol)
        assert not v_str.startswith("./reports"), "api service must not bind mount reports"
        assert not v_str.startswith("./logs"), "api service must not bind mount logs"


def test_required_env_example_block():
    assert ENV_EXAMPLE.exists(), ".env.example is missing"
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert REQUIRED_BLOCK in content, ".env.example must start with the exact required 8-line block"


def test_env_example_parity_with_settings():
    assert ENV_EXAMPLE.exists(), ".env.example is missing"
    example_lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    example_keys: set[str] = set()
    for line in example_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "=" in line, f"Line in .env.example must be KEY=value: {line}"
        key, _ = line.split("=", 1)
        example_keys.add(key.strip())

    settings_instance = Settings()
    settings_keys: set[str] = set()
    for attr in dir(settings_instance):
        if attr.startswith("_"):
            continue
        env_key = attr.upper()
        settings_keys.add(env_key)

    for env_key in settings_keys:
        assert env_key in example_keys, f"Settings attribute ({env_key}) missing from .env.example"

    for ex_key in example_keys:
        assert ex_key in settings_keys, f"Key {ex_key} in .env.example missing from Settings"
