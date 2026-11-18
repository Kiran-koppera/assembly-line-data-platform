"""Read-only API over the marts and the incident log (FastAPI).

    uvicorn assembly.api:app --reload      # http://localhost:8000/docs
"""
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException

from . import db

app = FastAPI(title="Assembly Line Data Platform", version="1.0.0",
              description="KPIs and data-quality incidents for a simulated general-assembly line.")


def q(sql: str, params: tuple = ()) -> list[dict]:
    with db.connect() as conn:
        cur = conn.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


@app.get("/health")
def health() -> dict:
    row = q("SELECT max(event_ts) AS latest_event, count(*) AS events FROM raw.events")[0]
    return {"status": "ok", **row}


@app.get("/kpis/summary")
def summary(day: Optional[date] = None) -> dict:
    day = day or q("SELECT max(day) AS d FROM marts.fct_first_pass_yield")[0]["d"]
    thr = q("SELECT sum(vehicles)::int AS vehicles, round(avg(vehicles), 1)::float AS avg_per_hour, max(target) AS target "
            "FROM marts.fct_hourly_throughput WHERE hour::date = %s", (day,))[0]
    fpy = q("SELECT first_pass_yield::float AS first_pass_yield FROM marts.fct_first_pass_yield WHERE day = %s", (day,))
    stop = q("SELECT coalesce(sum(stoppage_min), 0)::float AS stoppage_min FROM marts.fct_station_daily WHERE day = %s",
             (day,))[0]
    inc = q("SELECT count(*) AS open_incidents FROM monitoring.incidents WHERE status = 'open'")[0]
    return {"day": day, **thr, "first_pass_yield": fpy[0]["first_pass_yield"] if fpy else None, **stop, **inc}


@app.get("/throughput")
def throughput(day: date) -> list[dict]:
    return q("SELECT hour, vehicles, target, attainment FROM marts.fct_hourly_throughput "
             "WHERE hour::date = %s ORDER BY hour", (day,))


@app.get("/stations")
def stations(day: date) -> list[dict]:
    return q("SELECT * FROM marts.fct_station_daily WHERE day = %s ORDER BY p95_dwell_s DESC", (day,))


@app.get("/incidents")
def incidents(status: str = "open", limit: int = 100) -> list[dict]:
    return q("SELECT incident_id, run_id, check_name, severity, station_id, summary, detected_at, status "
             "FROM monitoring.incidents WHERE status = %s ORDER BY detected_at DESC LIMIT %s", (status, limit))


@app.get("/vehicles/{vin}")
def vehicle(vin: str) -> dict:
    events = q("SELECT event_ts, event_type, station_id, payload FROM raw.events WHERE vin = %s ORDER BY event_ts",
               (vin,))
    if not events:
        raise HTTPException(404, f"No events for {vin}")
    return {"vin": vin, "events": events}
