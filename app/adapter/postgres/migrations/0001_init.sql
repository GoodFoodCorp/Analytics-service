-- Cached KPI snapshots. analytics-service owns no business data of its own:
-- it aggregates what the other services expose, and only keeps the result
-- here so a dashboard refresh doesn't fan out to every service again.
CREATE TABLE IF NOT EXISTS metric_snapshots (
    scope_key   TEXT PRIMARY KEY,
    payload     JSONB       NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metric_snapshots_computed_at ON metric_snapshots (computed_at);
