"""Data-reliability checks that run after every load.

dbt tests guard the models (keys, ranges, relationships). These checks look for problems that
only show up across stations or over time, the kind that silently corrupt line KPIs:

| check                  | catches                                                      |
|------------------------|--------------------------------------------------------------|
| contract_violations    | records quarantined at ingestion (schema drift, bad fields)  |
| resent_events          | the same event delivered twice (network retry)               |
| duplicate_station_events | one vehicle reported twice at a station under new ids      |
| clock_skew             | a station whose clock runs ahead or behind its neighbours    |
| missing_station_records| vehicles that left the line without a record at a station    |
| station_silence        | a station that stops reporting while the line keeps running  |
| torque_level_shift     | a joint whose readings move away from target (e.g. units)    |
| late_arrivals          | events that arrived hours after they happened                |
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import psycopg

SKEW_S = 5.0            # median transfer time into a station should be ~0 s on a synchronous conveyor
SILENCE_MIN = 30        # a station quiet this long while vehicles pass it downstream
TORQUE_RATIO = (0.9, 1.1)
LATE_HOURS = 2


@dataclass
class Incident:
    check_name: str
    severity: str
    summary: str
    station_id: str | None = None
    details: dict = field(default_factory=dict)


def _rows(conn, sql, params=None):
    cur = conn.execute(sql, params or ())
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def run_checks(conn: psycopg.Connection, batch_ids: list[int] | None = None) -> list[Incident]:
    out: list[Incident] = []
    if batch_ids is None:
        batch_ids = [r[0] for r in conn.execute("SELECT batch_id FROM ops.ingest_batches").fetchall()]

    # 1. Contract violations
    for r in _rows(conn, "SELECT reason, count(*) AS n, min(file_path) AS example FROM raw.quarantine "
                         "WHERE batch_id = ANY(%s) GROUP BY reason ORDER BY n DESC", (batch_ids,)):
        out.append(Incident("contract_violations", "critical",
                            f"{r['n']} records quarantined: {r['reason']}", details=r))

    # 2. Re-sent events (dropped by the primary key at ingestion)
    dup = conn.execute("SELECT coalesce(sum(duplicates), 0) FROM ops.ingest_batches WHERE batch_id = ANY(%s)",
                       (batch_ids,)).fetchone()[0]
    if dup:
        out.append(Incident("resent_events", "warning", f"{dup} re-sent events ignored by idempotent load",
                            details={"duplicates": int(dup)}))

    # 3. Same vehicle reported twice at a station under different event ids
    for r in _rows(conn, """
        SELECT station_id, count(*) AS vehicles
        FROM intermediate.int_station_visits WHERE in_events > 1 OR out_events > 1
        GROUP BY station_id ORDER BY vehicles DESC"""):
        out.append(Incident("duplicate_station_events", "critical",
                            f"{r['vehicles']} vehicles reported more than once at {r['station_id']}",
                            r["station_id"], r))

    # 4. Clock skew: transfer time from the previous station's exit to this station's entry
    for r in _rows(conn, """
        WITH t AS (
            SELECT v.station_id,
                   extract(epoch FROM v.in_ts - p.out_ts) AS transfer_s
            FROM intermediate.int_station_visits v
            JOIN intermediate.int_station_visits p ON p.vin = v.vin AND p.sequence = v.sequence - 1
        )
        SELECT station_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY transfer_s) AS median_transfer_s,
               avg((transfer_s < 0)::int) AS share_negative, count(*) AS n
        FROM t GROUP BY station_id"""):
        if abs(r["median_transfer_s"]) > SKEW_S or r["share_negative"] > 0.01:
            out.append(Incident("clock_skew", "critical",
                                f"{r['station_id']}: median transfer {r['median_transfer_s']:+.0f} s, "
                                f"{100 * r['share_negative']:.1f}% negative", r["station_id"],
                                {k: float(v) for k, v in r.items() if k != "station_id"}))

    # 5. Vehicles that completed the line but have no record at a station
    for r in _rows(conn, """
        SELECT s.station_id, count(*) AS vehicles
        FROM intermediate.int_vehicle_journey j
        CROSS JOIN reference.dim_station s
        LEFT JOIN intermediate.int_station_visits v ON v.vin = j.vin AND v.station_id = s.station_id
        WHERE j.line_exit_ts IS NOT NULL AND v.vin IS NULL
        GROUP BY s.station_id ORDER BY vehicles DESC"""):
        out.append(Incident("missing_station_records", "critical",
                            f"{r['vehicles']} completed vehicles have no record at {r['station_id']}",
                            r["station_id"], r))

    # 6. Station silence: longest gap between a station's events while the line was producing
    for r in _rows(conn, f"""
        WITH ev AS (
            SELECT station_id, event_ts,
                   lead(event_ts) OVER (PARTITION BY station_id ORDER BY event_ts) AS next_ts
            FROM raw.events WHERE event_type IN ('station_in', 'station_out')
        ), gaps AS (
            SELECT station_id, event_ts AS gap_start, next_ts AS gap_end,
                   extract(epoch FROM next_ts - event_ts) / 60 AS gap_min
            FROM ev WHERE next_ts - event_ts > interval '{SILENCE_MIN} minutes'
        )
        -- Vehicles the neighbouring station handed over during the gap must have passed this station.
        -- (Upstream station_out for most stations; downstream station_in for the first station.)
        -- A whole-line pause, such as a break, silences both stations together and is not flagged.
        SELECT g.station_id, g.gap_start, g.gap_end, round(g.gap_min::numeric, 1) AS gap_min,
               (SELECT count(*) FROM raw.events e
                 WHERE e.event_ts > g.gap_start AND e.event_ts < g.gap_end
                   AND ((s.sequence > 1 AND e.event_type = 'station_out' AND e.station_id = up.station_id)
                     OR (s.sequence = 1 AND e.event_type = 'station_in' AND e.station_id = dn.station_id))
               ) AS handed_over
        FROM gaps g
        JOIN reference.dim_station s ON s.station_id = g.station_id
        LEFT JOIN reference.dim_station up ON up.sequence = s.sequence - 1
        LEFT JOIN reference.dim_station dn ON dn.sequence = s.sequence + 1"""):
        if r["handed_over"] > 5:
            out.append(Incident("station_silence", "critical",
                                f"{r['station_id']} silent for {r['gap_min']} min while its neighbour handed over "
                                f"{r['handed_over']} vehicles", r["station_id"], {k: str(v) for k, v in r.items()}))

    # 7. Torque readings drifting away from target (hourly, first attempts)
    lo, hi = TORQUE_RATIO
    for r in _rows(conn, """
        SELECT joint_id, station_id, date_trunc('hour', event_ts) AS hour,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY torque_nm / target_nm) AS median_ratio, count(*) AS n
        FROM staging.stg_torque_results WHERE attempt = 1
        GROUP BY joint_id, station_id, date_trunc('hour', event_ts) HAVING count(*) >= 10"""):
        if not lo <= r["median_ratio"] <= hi:
            out.append(Incident("torque_level_shift", "critical",
                                f"{r['joint_id']} at {r['hour']:%Y-%m-%d %H:00}: median {r['median_ratio']:.2f} × target",
                                r["station_id"], {k: str(v) for k, v in r.items()}))

    # 8. Late arrivals: events loaded in a later batch than events that happened after them
    late = _rows(conn, f"""
        WITH per_batch AS (                     -- latest event time each batch brought in
            SELECT batch_id, max(event_ts) AS max_ts FROM raw.events GROUP BY batch_id
        ), seen_before AS (                     -- latest event time known before each batch
            SELECT batch_id, max(max_ts) OVER (ORDER BY batch_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
                   AS prior_max_ts
            FROM per_batch
        )
        SELECT e.batch_id, count(*) AS n, min(e.event_ts) AS oldest
        FROM raw.events e
        JOIN seen_before s ON s.batch_id = e.batch_id
        WHERE e.batch_id = ANY(%s) AND e.event_ts < s.prior_max_ts - interval '{LATE_HOURS} hours'
        GROUP BY e.batch_id""", (batch_ids,))
    for r in late:
        out.append(Incident("late_arrivals", "warning", f"{r['n']} events arrived late in batch {r['batch_id']} "
                                                         f"(oldest {r['oldest']:%Y-%m-%d %H:%M}); models rebuilt",
                            details={k: str(v) for k, v in r.items()}))
    return _collapse(out)


def _collapse(incidents: list[Incident], keep: int = 5) -> list[Incident]:
    """Keep the worst few per check so one fault does not flood the log."""
    by: dict[str, list[Incident]] = {}
    for i in incidents:
        by.setdefault(i.check_name, []).append(i)
    out = []
    for name, items in by.items():
        out.extend(items[:keep])
        if len(items) > keep:
            out.append(Incident(name, items[0].severity, f"... and {len(items) - keep} more {name} findings"))
    return out


def record(conn: psycopg.Connection, run_id: str, incidents: list[Incident]) -> None:
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO monitoring.incidents (run_id, check_name, severity, station_id, summary, details) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        [(run_id, i.check_name, i.severity, i.station_id, i.summary, json.dumps(i.details, default=str))
                         for i in incidents])
    conn.commit()


def as_dicts(incidents: list[Incident]) -> list[dict]:
    return [asdict(i) for i in incidents]
