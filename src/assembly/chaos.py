"""Fault drills: inject realistic data faults into a simulated day and measure what gets caught.

Each scenario starts from the same clean simulated day, applies one fault the way it happens in a
plant, runs the full pipeline (ingest -> dbt -> monitoring) on a fresh database, and records which
checks fired. A drill passes when the expected check fires and no unrelated critical check does.
"""
from __future__ import annotations

import copy
import json
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import db, monitoring, pipeline
from .config import RunConfig
from .ingest import ingest
from .simulator import simulate, write_landing


def _hour(e) -> int:
    return int(e["ts"][11:13])


def _shift(ts: str, seconds: int) -> str:
    from datetime import datetime, timedelta
    t = datetime.fromisoformat(ts.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def clock_drift(ev):
    """F07's PLC clock jumps 3 minutes ahead at 10:00 and stays wrong."""
    for e in ev:
        if e["station_id"] == "F07" and e["source"] == "plc" and _hour(e) >= 10:
            e["ts"] = _shift(e["ts"], 180)
    return ev


def resend_burst(ev):
    """Network retry: the torque gateway re-sends 500 events it already delivered (same event ids)."""
    burst = [copy.deepcopy(e) for e in ev if e["event_type"] == "torque_result" and _hour(e) == 11][:500]
    return ev + burst


def duplicate_new_ids(ev):
    """A PLC restart replays an hour of station_in signals at C03 with freshly generated event ids."""
    replay = [dict(copy.deepcopy(e), event_id=str(uuid.uuid4())) for e in ev
              if e["station_id"] == "C03" and e["event_type"] == "station_in" and _hour(e) == 15][:100]
    return ev + replay


def station_dropout(ev):
    """C04's PLC stops sending between 12:00 and 13:00 while the line keeps running."""
    return [e for e in ev if not (e["station_id"] == "C04" and e["source"] == "plc" and _hour(e) == 12)]


def unit_change(ev):
    """A torque tool at C05 gets new firmware at 14:00 and reports lbf·ft in the torque_nm field."""
    for e in ev:
        if e["event_type"] == "torque_result" and e["station_id"] == "C05" and _hour(e) >= 14:
            e["torque_nm"] = round(e["torque_nm"] * 0.7376, 2)
    return ev


def schema_drift(ev):
    """Firmware renames torque_nm to torque_value on C06's tool between 08:00 and 09:00."""
    for e in ev:
        if e["event_type"] == "torque_result" and e["station_id"] == "C06" and _hour(e) == 8:
            e["torque_value"] = e.pop("torque_nm")
    return ev


@dataclass
class Scenario:
    name: str
    description: str
    expected: set[str]
    inject: Callable | None = None
    late_hour: int | None = None


SCENARIOS = [
    Scenario("baseline", "Clean day, no fault (measures false alarms)", set()),
    Scenario("clock_drift", clock_drift.__doc__, {"clock_skew"}, clock_drift),
    Scenario("resend_burst", resend_burst.__doc__, {"resent_events"}, resend_burst),
    Scenario("duplicate_new_ids", duplicate_new_ids.__doc__, {"duplicate_station_events"}, duplicate_new_ids),
    Scenario("station_dropout", station_dropout.__doc__, {"missing_station_records", "station_silence"},
             station_dropout),
    Scenario("unit_change", unit_change.__doc__, {"torque_level_shift"}, unit_change),
    Scenario("schema_drift", schema_drift.__doc__, {"contract_violations"}, schema_drift),
    Scenario("late_arrival", "Files for 03:00-04:00 reach the landing zone six hours late", {"late_arrivals"},
             late_hour=3),
]


def run_drill(sc: Scenario, clean: list[dict], workdir: Path) -> dict:
    t0 = time.time()
    events = sc.inject(copy.deepcopy(clean)) if sc.inject else copy.deepcopy(clean)
    landing = workdir / sc.name
    shutil.rmtree(landing, ignore_errors=True)
    held = []
    if sc.late_hour is not None:
        held = [e for e in events if _hour(e) == sc.late_hour]
        events = [e for e in events if _hour(e) != sc.late_hour]
    write_landing(events, landing)
    with db.connect() as conn:
        pipeline.reset(conn)
        ingest(conn, landing)
        if held:  # the late files arrive and the next scheduled load picks them up
            write_landing(held, landing)
            ingest(conn, landing)
        tr = pipeline.transform()
        incidents = monitoring.run_checks(conn)
        monitoring.record(conn, f"drill-{sc.name}", incidents)
    fired = {i.check_name for i in incidents}
    unexpected = {i.check_name for i in incidents if i.severity == "critical"} - sc.expected
    detected = sc.expected <= fired if sc.expected else not fired
    return {"scenario": sc.name, "description": sc.description, "expected": sorted(sc.expected),
            "fired": sorted(fired), "dbt_test_failures": tr["test_failures"], "detected": detected,
            "false_alarms": sorted(unexpected), "passed": detected and not unexpected,
            "summaries": [i.summary for i in incidents][:6], "seconds": round(time.time() - t0, 1)}


def run_all(workdir: Path, out: Path, cfg: RunConfig | None = None) -> list[dict]:
    clean = simulate(cfg or RunConfig(days=1))
    results = [run_drill(sc, clean, workdir) for sc in SCENARIOS]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    return results
