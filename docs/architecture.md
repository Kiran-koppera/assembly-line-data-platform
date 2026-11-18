# Architecture and decisions

```
Simulator (SimPy)        40 stations · PLC, torque, andon, quality, EOL events
   │  JSON lines, hourly files: landing/date=…/hour=…/<source>.jsonl
   ▼
Ingestion (Python)       contract check → COPY into a temp table → INSERT … ON CONFLICT DO NOTHING
   │                     bad records → raw.quarantine · file checksums → ops.ingested_files
   ▼
PostgreSQL               raw.events, partitioned by day, PK (event_id, event_ts), 3 indexes
   ▼
dbt                      staging (views) → intermediate (tables) → marts (tables), 26 tests, docs
   ▼
Monitoring (SQL)         8 checks → monitoring.incidents
   ▼
Serving                  FastAPI (local) · JSON export → static dashboard + dbt docs on GitHub Pages
```

## Decisions

**1. PostgreSQL with daily range partitions.** The job asks for PostgreSQL, and line data is
naturally time-ordered: partitions keep each day's scans small and make retention simple (drop a
partition). The primary key must include the partition key, so it is `(event_id, event_ts)`; a
re-sent event carries the same timestamp, so exact duplicates are still rejected.

**2. Envelope columns plus a JSONB payload.** Every event shares the envelope (id, time, type,
vehicle, station); type-specific fields live in JSONB. New event types do not need migrations,
and hot JSON paths get expression indexes (see benchmarks).

**3. Data contract at ingestion, quarantine instead of drop.** Invalid records are kept with a
reason, so a mapping fix can replay them. Silently dropping them would hide the problem.

**4. Idempotency at two levels.** File checksums skip unchanged files; the primary key absorbs
re-sent events. Re-running any load is safe.

**5. dbt for transformations.** SQL models with tests and generated documentation (lineage,
column descriptions) cover "document dashboards and data processing" as a by-product of the work.

**6. Cross-station checks outside dbt.** dbt tests guard each model; clock skew, station silence
and torque level shifts compare stations or hours with each other, which is clearer as dedicated
SQL checks writing to an incident table.

**7. Embedded PostgreSQL locally, the official image in CI.** `pgserver` runs a real PostgreSQL
16 with no system install; CI uses `postgres:16` as a service container. Both run the same code.

**8. Static dashboard.** Free to host, fast, and it shows exactly the data the pipeline produced;
the FastAPI service serves the same marts for local or internal use.
