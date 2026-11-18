"""Discrete-event simulation of a paced general-assembly line (SimPy).

Vehicles are released at takt. Each station holds one vehicle; a vehicle only leaves a station
once the next station is free (blocking), so a slow station or a stoppage backs up the line the
way it does on a real conveyor. Every action emits an event in the shape a plant's systems send
them (PLC station in/out, torque tool results, andon calls, quality gates, end-of-line tests).

Output: JSON-lines files partitioned by hour, under landing/date=YYYY-MM-DD/hour=HH/<source>.jsonl
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import simpy

from . import config as C


class Line:
    def __init__(self, env: simpy.Environment, cfg: C.RunConfig):
        self.env, self.cfg = env, cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.t0 = datetime.fromisoformat(cfg.start.replace("Z", "+00:00"))
        self.stations = cfg.stations
        self.res = [simpy.PriorityResource(env, capacity=1) for _ in self.stations]
        self.events: list[dict] = []
        self.vin_seq = 0
        self.uuid_rng = np.random.default_rng(cfg.seed + 1)

    # ---------------------------------------------------------------- helpers
    def ts(self) -> str:
        return (self.t0 + timedelta(seconds=self.env.now)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def emit(self, source: str, event_type: str, vin: str | None, station: str | None, **payload) -> None:
        eid = str(uuid.UUID(bytes=self.uuid_rng.bytes(16), version=4))
        self.events.append({"event_id": eid, "schema_version": C.SCHEMA_VERSION, "source": source,
                            "event_type": event_type, "ts": self.ts(), "vin": vin, "station_id": station,
                            **payload})

    def in_break(self, t: float) -> bool:
        now = self.t0 + timedelta(seconds=t)
        for h, m, dur in C.BREAKS:
            start = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if start <= now < start + timedelta(minutes=dur):
                return True
        return False

    # ---------------------------------------------------------------- processes
    def release(self):
        horizon = self.cfg.days * 86400
        while self.env.now < horizon:
            if self.in_break(self.env.now):
                yield self.env.timeout(30)
                continue
            if self.res[0].count or self.res[0].queue:  # first station still occupied: line is backed up
                yield self.env.timeout(5)
                continue
            self.vin_seq += 1
            self.env.process(self.vehicle(f"SIM{self.vin_seq:09d}"))
            yield self.env.timeout(C.TAKT_S)

    def andon(self, i: int):
        st = self.stations[i]
        while True:
            yield self.env.timeout(self.rng.exponential(C.ANDON_MTBF_MIN * 60))
            with self.res[i].request(priority=0) as req:  # stoppage takes the station first
                yield req
                reason = str(self.rng.choice(C.ANDON_REASONS))
                dur = max(30.0, self.rng.exponential(C.ANDON_MTTR_MIN * 60))
                aid = f"A-{st.station_id}-{int(self.env.now)}"
                self.emit("andon", "andon_start", None, st.station_id, andon_id=aid, reason=reason)
                yield self.env.timeout(dur)
                self.emit("andon", "andon_end", None, st.station_id, andon_id=aid, reason=reason)

    def vehicle(self, vin: str):
        held = None
        failed_eol = False
        for i, st in enumerate(self.stations):
            req = self.res[i].request(priority=1)
            yield req
            if held is not None:
                self.res[i - 1].release(held)
                self.emit("plc", "station_out", vin, self.stations[i - 1].station_id)
            self.emit("plc", "station_in", vin, st.station_id)
            cycle = st.base_cycle_s * self.rng.lognormal(0, C.CYCLE_SIGMA)
            yield self.env.timeout(cycle * 0.7)
            for j in st.joints:
                self.tighten(vin, st, j)
            if st.eol_test:
                passed = self.rng.random() >= C.EOL_FAIL_RATE[st.eol_test]
                failed_eol |= not passed
                self.emit("eol", "eol_test", vin, st.station_id, test=st.eol_test, result="pass" if passed else "fail")
            elif st.quality_gate:
                ok = self.rng.random() < C.QUALITY_GATE_PASS
                self.emit("quality", "quality_check", vin, st.station_id, result="pass" if ok else "fail",
                          defect_code=None if ok else str(self.rng.choice(["gap_flush", "scratch", "missing_clip",
                                                                                 "connector_unseated"])))
            yield self.env.timeout(cycle * 0.3)
            held = req
        self.res[-1].release(held)
        self.emit("plc", "station_out", vin, self.stations[-1].station_id)
        if failed_eol:  # off-line rework, then retest
            yield self.env.timeout(self.rng.uniform(20, 90) * 60)
            self.emit("eol", "eol_retest", vin, "E06", test="final_inspection", result="pass")

    def tighten(self, vin: str, st: C.Station, j: C.Joint) -> None:
        for attempt in (1, 2):
            val = self.rng.normal(j.target_nm, j.target_nm * C.TORQUE_SIGMA_PCT / 100)
            lo, hi = j.target_nm * (1 - j.tolerance_pct / 100), j.target_nm * (1 + j.tolerance_pct / 100)
            ok = lo <= val <= hi
            self.emit("torque", "torque_result", vin, st.station_id, joint_id=j.joint_id, torque_nm=round(val, 2),
                      target_nm=j.target_nm, lower_nm=round(lo, 2), upper_nm=round(hi, 2), attempt=attempt,
                      result="OK" if ok else "NOK")
            if ok:
                return


def simulate(cfg: C.RunConfig) -> list[dict]:
    env = simpy.Environment()
    line = Line(env, cfg)
    env.process(line.release())
    for i in range(len(line.stations)):
        env.process(line.andon(i))
    env.run(until=cfg.days * 86400 + 3 * 3600)  # let the last vehicles finish
    line.events.sort(key=lambda e: e["ts"])
    return line.events


def write_landing(events: list[dict], root: Path) -> dict[str, int]:
    """Partition by event hour and source, like files dropped by an edge gateway."""
    buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for e in events:
        d, h = e["ts"][:10], e["ts"][11:13]
        buckets[(d, h, e["source"])].append(json.dumps(e, separators=(",", ":")))
    for (d, h, src), lines in buckets.items():
        p = root / f"date={d}" / f"hour={h}"
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{src}.jsonl").write_text("\n".join(lines) + "\n")
    return {"files": len(buckets), "events": len(events)}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
