"""Export mart data, incidents, drill and benchmark results as JSON for the static dashboard."""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from . import db

ROOT = db.ROOT


def _default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def _rows(conn, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def export(site: Path) -> dict:
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(ROOT / "web", site)
    data = site / "data"
    data.mkdir(exist_ok=True)
    with db.connect() as conn:
        tables = {
            "throughput": "SELECT * FROM marts.fct_hourly_throughput ORDER BY hour",
            "stations": "SELECT * FROM marts.fct_station_daily ORDER BY day, station_id",
            "fpy": "SELECT * FROM marts.fct_first_pass_yield ORDER BY day",
            "torque": "SELECT * FROM marts.fct_torque_capability ORDER BY cpk NULLS LAST",
            "incidents": "SELECT check_name, severity, station_id, summary, detected_at FROM monitoring.incidents "
                         "WHERE run_id NOT LIKE 'drill-%' ORDER BY detected_at DESC LIMIT 200",
            "batches": "SELECT * FROM ops.ingest_batches ORDER BY batch_id",
            "meta": "SELECT min(event_ts) AS first_event, max(event_ts) AS last_event, count(*) AS events, "
                    "count(DISTINCT vin) AS vehicles FROM raw.events",
        }
        out = {name: _rows(conn, sql) for name, sql in tables.items()}
    for extra in ("fault-drills.json", "benchmarks.json"):
        src = ROOT / "output" / extra
        if src.exists():
            out[extra.removesuffix(".json").replace("-", "_")] = json.loads(src.read_text())
    for name, rows in out.items():
        (data / f"{name}.json").write_text(json.dumps(rows, default=_default))
    return {k: len(v) if isinstance(v, list) else 1 for k, v in out.items()}
