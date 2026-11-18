"""SQL optimization benchmark on raw.events.

Four queries an assembly data team runs every day. Each is timed with EXPLAIN (ANALYZE) as the
median of several runs, first without secondary indexes and then with the indexes defined in
sql/indexes.sql. Results (and the plan node used) go to output/benchmarks.json.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import psycopg

from .db import ROOT

INDEXES_SQL = ROOT / "sql" / "indexes.sql"
INDEX_NAMES = ["events_station_type_ts_idx", "events_vin_idx", "events_torque_joint_idx"]

QUERIES = {
    "hourly_throughput": (
        "Vehicles leaving the line per hour on one day",
        """SELECT date_trunc('hour', event_ts) AS hour, count(*)
           FROM raw.events
           WHERE station_id = 'E06' AND event_type = 'station_out'
             AND event_ts >= %(day)s AND event_ts < %(day)s::date + 1
           GROUP BY 1 ORDER BY 1"""),
    "station_dwell": (
        "Median and p95 dwell time at one station over a day",
        """WITH v AS (
             SELECT vin, min(event_ts) FILTER (WHERE event_type = 'station_in') AS t_in,
                         min(event_ts) FILTER (WHERE event_type = 'station_out') AS t_out
             FROM raw.events
             WHERE station_id = 'C05' AND event_type IN ('station_in', 'station_out')
               AND event_ts >= %(day)s AND event_ts < %(day)s::date + 1
             GROUP BY vin)
           SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM t_out - t_in)),
                  percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM t_out - t_in))
           FROM v"""),
    "torque_joint_week": (
        "Mean, spread and NOK count for one torque joint over the whole week",
        """SELECT avg((payload->>'torque_nm')::numeric), stddev_samp((payload->>'torque_nm')::numeric),
                  count(*) FILTER (WHERE payload->>'result' = 'NOK')
           FROM raw.events
           WHERE event_type = 'torque_result' AND payload->>'joint_id' = 'C05-J1'"""),
    "vehicle_history": (
        "Full event history of one vehicle (troubleshooting lookup)",
        """SELECT event_ts, event_type, station_id, payload FROM raw.events
           WHERE vin = %(vin)s ORDER BY event_ts"""),
}


def _plan_time(conn: psycopg.Connection, sql: str, params: dict) -> tuple[float, str]:
    plan = conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params).fetchone()[0][0]
    nodes, stack = [], [plan["Plan"]]
    while stack:
        n = stack.pop()
        nodes.append(n["Node Type"])
        stack.extend(n.get("Plans", []))
    scan = next((t for t in nodes if "Scan" in t), nodes[-1])
    return plan["Execution Time"], scan


def measure(conn: psycopg.Connection, params: dict, runs: int = 7) -> dict:
    out = {}
    for name, (_, sql) in QUERIES.items():
        _plan_time(conn, sql, params)  # warm the cache
        times, scan = [], ""
        for _ in range(runs):
            t, scan = _plan_time(conn, sql, params)
            times.append(t)
        out[name] = {"median_ms": round(statistics.median(times), 2), "scan": scan}
    return out


def run(conn: psycopg.Connection, out: Path, runs: int = 7) -> dict:
    day = conn.execute("SELECT min(event_ts)::date + 1 FROM raw.events").fetchone()[0].isoformat()
    vin = conn.execute("SELECT vin FROM raw.events WHERE event_type = 'station_out' AND station_id = 'E06' "
                       "ORDER BY event_ts LIMIT 1 OFFSET 500").fetchone()[0]
    rows = conn.execute("SELECT count(*) FROM raw.events").fetchone()[0]
    params = {"day": day, "vin": vin}

    for name in INDEX_NAMES:
        conn.execute(f"DROP INDEX IF EXISTS raw.{name}")
    conn.execute("ANALYZE raw.events")
    conn.commit()
    before = measure(conn, params, runs)

    conn.execute(INDEXES_SQL.read_text())
    conn.execute("ANALYZE raw.events")
    conn.commit()
    after = measure(conn, params, runs)

    result = {"rows": rows, "runs_per_query": runs, "params": params, "queries": [
        {"query": name, "description": QUERIES[name][0], "before_ms": before[name]["median_ms"],
         "before_scan": before[name]["scan"], "after_ms": after[name]["median_ms"], "after_scan": after[name]["scan"],
         "speedup": round(before[name]["median_ms"] / max(after[name]["median_ms"], 0.001), 1)}
        for name in QUERIES]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    return result
