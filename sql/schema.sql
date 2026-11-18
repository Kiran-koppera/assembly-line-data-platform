-- Landing schema for line events. Idempotent: safe to run on every start.
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS monitoring;

-- All events, partitioned by day. The primary key makes re-sent events (same event_id) harmless.
CREATE TABLE IF NOT EXISTS raw.events (
    event_id        uuid        NOT NULL,
    event_ts        timestamptz NOT NULL,
    event_type      text        NOT NULL,
    source          text        NOT NULL,
    vin             text,
    station_id      text,
    schema_version  text        NOT NULL,
    payload         jsonb       NOT NULL,
    batch_id        bigint      NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, event_ts)
) PARTITION BY RANGE (event_ts);

-- Records that break the data contract are kept, not dropped, so they can be fixed and replayed.
CREATE TABLE IF NOT EXISTS raw.quarantine (
    id          bigserial PRIMARY KEY,
    batch_id    bigint      NOT NULL,
    file_path   text        NOT NULL,
    line_no     int         NOT NULL,
    reason      text        NOT NULL,
    raw_line    text        NOT NULL,
    loaded_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.ingest_batches (
    batch_id     bigserial PRIMARY KEY,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    files        int, lines_read int, loaded int, duplicates int, quarantined int,
    max_event_ts timestamptz
);

-- One row per landing file: unchanged files are skipped, changed files are re-read (dedup by key).
CREATE TABLE IF NOT EXISTS ops.ingested_files (
    file_path   text PRIMARY KEY,
    sha256      text        NOT NULL,
    batch_id    bigint      NOT NULL,
    lines       int         NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS monitoring.incidents (
    incident_id  bigserial PRIMARY KEY,
    run_id       text        NOT NULL,
    check_name   text        NOT NULL,
    severity     text        NOT NULL CHECK (severity IN ('critical', 'warning')),
    station_id   text,
    summary      text        NOT NULL,
    details      jsonb       NOT NULL DEFAULT '{}',
    detected_at  timestamptz NOT NULL DEFAULT now(),
    status       text        NOT NULL DEFAULT 'open'
);
