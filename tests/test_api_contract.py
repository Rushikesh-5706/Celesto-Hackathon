"""FastAPI API contract compliance tests verifying exact endpoint behaviors."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reprobox.api.app import app
from reprobox.ledger.database import apply_seed_sql, wait_for_db

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "seeds" / "01_runs.sql"


@pytest.fixture(scope="module")
def db_available() -> bool:
    """Return True only if PostgreSQL is reachable within a short timeout."""
    return wait_for_db(max_wait_s=5)


@pytest.fixture(scope="module", autouse=True)
def init_test_db(db_available: bool):
    """Ensure schema and seed are applied to the test database when available."""
    if db_available:
        apply_seed_sql(SEED_PATH)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_health_contract(client: TestClient):
    """GET /health must return HTTP 200 with exactly {'status': 'ok'}."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_runs_includes_seed(client: TestClient, db_available: bool):
    """GET /api/runs must return 200 and include seed row sbx-seeddemo1."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert isinstance(runs, list)
    assert any(r.get("sandbox_name") == "sbx-seeddemo1" for r in runs)


def test_post_runs_valid_and_idempotent(client: TestClient, db_available: bool):
    """POST /api/runs must return 201 on valid input and repeat idempotently."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    payload = {
        "run_id": "run-contract-test1",
        "sandbox_name": "sbx-contracttest1",
        "problem_id": "contract-test",
        "state": "created",
        "execution_target": "celesto_sandbox",
    }
    resp1 = client.post("/api/runs", json=payload)
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["run_id"] == payload["run_id"]
    assert data1["sandbox_name"] == payload["sandbox_name"]

    # Repeating POST with same run_id must also return 201 without error
    resp2 = client.post("/api/runs", json=payload)
    assert resp2.status_code == 201
    assert resp2.json()["run_id"] == payload["run_id"]


def test_post_runs_unknown_extra_fields_ignored(client: TestClient, db_available: bool):
    """POST /api/runs ignores extra unexpected fields and returns 201."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    payload = {
        "run_id": "run-contract-extra",
        "sandbox_name": "sbx-contractextra",
        "problem_id": "contract-test",
        "state": "ready",
        "execution_target": "celesto_sandbox",
        "unexpected_field": "should_be_ignored",
        "another_field": 12345,
    }
    resp = client.post("/api/runs", json=payload)
    assert resp.status_code == 201


def test_post_runs_validation_rejections(client: TestClient):
    """Invalid requests must return HTTP 400 (never 422)."""
    base = {
        "run_id": "run-contract-bad",
        "sandbox_name": "sbx-contractbad1",
        "problem_id": "contract-test",
        "state": "created",
        "execution_target": "celesto_sandbox",
    }

    # Wrong execution target
    bad_target = {**base, "execution_target": "host"}
    assert client.post("/api/runs", json=bad_target).status_code == 400

    # Unknown state
    bad_state = {**base, "state": "unknown_state"}
    assert client.post("/api/runs", json=bad_state).status_code == 400

    # Bad sandbox name (fails regex)
    bad_name = {**base, "sandbox_name": "bad-name"}
    assert client.post("/api/runs", json=bad_name).status_code == 400

    # Missing field
    missing_field = {k: v for k, v in base.items() if k != "problem_id"}
    assert client.post("/api/runs", json=missing_field).status_code == 400

    # Empty string
    empty_str = {**base, "run_id": ""}
    assert client.post("/api/runs", json=empty_str).status_code == 400

    # Malformed JSON
    resp_malformed = client.post(
        "/api/runs",
        content="not-a-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp_malformed.status_code == 400


def test_seed_sql_idempotency(client: TestClient, db_available: bool):
    """Applying seed SQL twice must maintain exactly one seed row."""
    if not db_available:
        pytest.skip("PostgreSQL not available")
    apply_seed_sql(SEED_PATH)
    apply_seed_sql(SEED_PATH)

    resp = client.get("/api/runs")
    seed_rows = [r for r in resp.json() if r.get("sandbox_name") == "sbx-seeddemo1"]
    assert len(seed_rows) == 1
