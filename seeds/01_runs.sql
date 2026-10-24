CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT        PRIMARY KEY,
    sandbox_name    TEXT        NOT NULL
                                CHECK (sandbox_name ~ '^sbx-[a-z0-9]{8,}$'),
    problem_id      TEXT        NOT NULL,
    state           TEXT        NOT NULL
                                CHECK (state IN (
                                    'created', 'ready', 'running',
                                    'succeeded', 'failed', 'deleted'
                                )),
    execution_target TEXT       NOT NULL
                                CHECK (execution_target = 'celesto_sandbox'),
    outcome         TEXT        NULL
                                CHECK (outcome IN ('succeeded', 'failed')),
    computer_id     TEXT        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE runs ADD COLUMN IF NOT EXISTS computer_id TEXT;

CREATE INDEX IF NOT EXISTS idx_runs_sandbox_name ON runs (sandbox_name);

CREATE TABLE IF NOT EXISTS run_events (
    id      BIGSERIAL   PRIMARY KEY,
    run_id  TEXT        NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    event   TEXT        NOT NULL,
    payload JSONB       NOT NULL DEFAULT '{}'
);

INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target, outcome)
SELECT
    'run-seeddemo1',
    'sbx-seeddemo1',
    'seed-demo',
    'deleted',
    'celesto_sandbox',
    'succeeded'
WHERE NOT EXISTS (
    SELECT 1 FROM runs WHERE run_id = 'run-seeddemo1'
);
