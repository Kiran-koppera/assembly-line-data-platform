"""Run the platform end to end: simulate -> (inject faults) -> ingest -> dbt -> monitor."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from . import db, monitoring
from .config import RunConfig
from .ingest import ingest
from .simulator import simulate, write_landing

ROOT = db.ROOT
DBT = [str(ROOT / ".venv" / "bin" / "dbt") if (ROOT / ".venv" / "bin" / "dbt").exists() else "dbt"]


def dbt(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **db.dbt_env()}
    return subprocess.run([*DBT, *args, "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt")],
                          env=env, capture_output=True, text=True)


def dbt_failures(proc: subprocess.CompletedProcess) -> list[str]:
    """Names of failed dbt tests, read from dbt's own run results (not from coloured console output)."""
    import json

    path = ROOT / "dbt" / "target" / "run_results.json"
    if not path.exists():
        return []
    results = json.loads(path.read_text()).get("results", [])
    return sorted(r["unique_id"].split(".")[2] for r in results if r.get("status") in ("fail", "error"))


def reset(conn) -> None:
    conn.execute("DROP SCHEMA IF EXISTS raw, ops, monitoring, staging, intermediate, marts, reference CASCADE")
    conn.commit()
    db.init_schema(conn)


def transform() -> dict:
    t = time.time()
    seed, run, test = dbt("seed"), dbt("run"), dbt("test")
    if run.returncode:
        raise RuntimeError("dbt run failed:\n" + run.stdout[-3000:])
    return {"seconds": round(time.time() - t, 2), "seed_ok": seed.returncode == 0,
            "test_failures": dbt_failures(test), "tests_ok": test.returncode == 0}


def run_all(landing: Path, cfg: RunConfig | None = None, fresh: bool = True, simulate_data: bool = True) -> dict:
    timings = {}
    if simulate_data:
        t = time.time()
        shutil.rmtree(landing, ignore_errors=True)
        stats = write_landing(simulate(cfg or RunConfig()), landing)
        timings["simulate_s"] = round(time.time() - t, 2)
    with db.connect() as conn:
        if fresh:
            reset(conn)
        res = ingest(conn, landing)
        tr = transform()
        incidents = monitoring.run_checks(conn)
        monitoring.record(conn, f"run-{res.batch_id}", incidents)
    return {"ingest": res.__dict__, "transform": tr, "incidents": monitoring.as_dicts(incidents),
            "simulate": stats if simulate_data else None, **timings}
