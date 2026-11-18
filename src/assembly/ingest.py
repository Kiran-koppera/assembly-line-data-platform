"""Load landing files into PostgreSQL.

* Idempotent: a file whose checksum was already ingested is skipped; a changed or re-delivered
  file is re-read and duplicate events are dropped by the primary key (event_id, event_ts).
* Late data: files for past hours are simply loaded when they arrive; partitions are created on
  demand, and downstream models rebuild from raw.
* Bad records: contract violations and unparseable lines go to raw.quarantine with a reason.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg

from .contract import payload, validate


@dataclass
class BatchResult:
    batch_id: int
    files: int = 0
    skipped_files: int = 0
    lines_read: int = 0
    loaded: int = 0
    duplicates: int = 0
    quarantined: int = 0
    seconds: float = 0.0


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ensure_partitions(conn: psycopg.Connection, dates: set[str]) -> None:
    for d in sorted(dates):
        name = "events_" + d.replace("-", "")
        conn.execute(f"CREATE TABLE IF NOT EXISTS raw.{name} PARTITION OF raw.events "
                     f"FOR VALUES FROM ('{d} 00:00:00+00') TO (('{d}'::date + 1)::timestamp AT TIME ZONE 'UTC')")


def ingest(conn: psycopg.Connection, landing: Path) -> BatchResult:
    t0 = time.time()
    batch_id = conn.execute("INSERT INTO ops.ingest_batches DEFAULT VALUES RETURNING batch_id").fetchone()[0]
    res = BatchResult(batch_id)
    known = dict(conn.execute("SELECT file_path, sha256 FROM ops.ingested_files").fetchall())
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS stage (LIKE raw.events INCLUDING DEFAULTS) ON COMMIT DROP")

    for path in sorted(landing.rglob("*.jsonl")):
        rel = str(path.relative_to(landing))
        digest = _sha256(path)
        if known.get(rel) == digest:
            res.skipped_files += 1
            continue
        res.files += 1
        good, bad, dates = [], [], set()
        lines = path.read_text().splitlines()
        for n, line in enumerate(lines, 1):
            if not line.strip():
                continue
            res.lines_read += 1
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                bad.append((n, "invalid JSON", line))
                continue
            reason = validate(e) if isinstance(e, dict) else "not a JSON object"
            if reason:
                bad.append((n, reason, line))
                continue
            dates.add(e["ts"][:10])
            good.append((e["event_id"], e["ts"], e["event_type"], e["source"], e.get("vin"), e.get("station_id"),
                         e["schema_version"], json.dumps(payload(e)), batch_id))
        ensure_partitions(conn, dates)
        if good:
            conn.execute("TRUNCATE stage")
            with conn.cursor().copy("COPY stage (event_id, event_ts, event_type, source, vin, station_id, "
                                    "schema_version, payload, batch_id) FROM STDIN") as cp:
                for row in good:
                    cp.write_row(row)
            inserted = conn.execute("INSERT INTO raw.events SELECT * FROM stage ON CONFLICT DO NOTHING").rowcount
            res.loaded += inserted
            res.duplicates += len(good) - inserted
        if bad:
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO raw.quarantine (batch_id, file_path, line_no, reason, raw_line) "
                                "VALUES (%s, %s, %s, %s, %s)", [(batch_id, rel, n, r, raw) for n, r, raw in bad])
            res.quarantined += len(bad)
        conn.execute("INSERT INTO ops.ingested_files (file_path, sha256, batch_id, lines) VALUES (%s, %s, %s, %s) "
                     "ON CONFLICT (file_path) DO UPDATE SET sha256 = EXCLUDED.sha256, batch_id = EXCLUDED.batch_id, "
                     "lines = EXCLUDED.lines, ingested_at = now()", (rel, digest, batch_id, len(lines)))

    res.seconds = round(time.time() - t0, 2)
    conn.execute("UPDATE ops.ingest_batches SET finished_at = now(), files = %s, lines_read = %s, loaded = %s, "
                 "duplicates = %s, quarantined = %s, max_event_ts = (SELECT max(event_ts) FROM raw.events) "
                 "WHERE batch_id = %s",
                 (res.files, res.lines_read, res.loaded, res.duplicates, res.quarantined, batch_id))
    conn.commit()
    return res
