"""Command line.

    python -m assembly run --days 3        simulate, ingest, dbt build, monitor (fresh database)
    python -m assembly drills              fault-injection drills -> output/fault-drills.json
    python -m assembly bench --days 7      SQL benchmark on a week of data -> output/benchmarks.json
    python -m assembly export              dashboard + data -> site/
    python -m assembly docs                dbt docs -> site/dbt-docs/
"""
from __future__ import annotations

import argparse
import json
import shutil

from . import benchmark, chaos, db, export, pipeline
from .config import RunConfig
from .ingest import ingest
from .simulator import simulate, write_landing

ROOT = db.ROOT


def main() -> None:
    ap = argparse.ArgumentParser(prog="assembly")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--days", type=float, default=3)
    r.add_argument("--seed", type=int, default=42)
    sub.add_parser("drills")
    b = sub.add_parser("bench")
    b.add_argument("--days", type=float, default=7)
    sub.add_parser("export")
    sub.add_parser("docs")
    a = ap.parse_args()

    if a.cmd == "run":
        res = pipeline.run_all(ROOT / "landing", RunConfig(days=a.days, seed=a.seed))
        print(json.dumps({k: v for k, v in res.items() if k != "incidents"}, indent=2, default=str))
        print(f"incidents: {len(res['incidents'])}")
        if not res["transform"]["tests_ok"]:
            raise SystemExit("dbt tests failed: " + ", ".join(res["transform"]["test_failures"]))
    elif a.cmd == "drills":
        results = chaos.run_all(ROOT / ".drills", ROOT / "output" / "fault-drills.json")
        for x in results:
            print(f"{'PASS' if x['passed'] else 'FAIL'}  {x['scenario']:18} fired={x['fired']}")
        if not all(x["passed"] for x in results):
            raise SystemExit("a fault drill failed")
    elif a.cmd == "bench":
        landing = ROOT / ".bench"
        shutil.rmtree(landing, ignore_errors=True)
        write_landing(simulate(RunConfig(days=a.days)), landing)
        with db.connect() as conn:
            pipeline.reset(conn)
            ingest(conn, landing)
            print(json.dumps(benchmark.run(conn, ROOT / "output" / "benchmarks.json"), indent=2))
    elif a.cmd == "export":
        print(export.export(ROOT / "site"))
    elif a.cmd == "docs":
        proc = pipeline.dbt("docs", "generate", "--static")
        if proc.returncode:
            raise SystemExit(proc.stdout[-2000:])
        dest = ROOT / "site" / "dbt-docs"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "dbt" / "target" / "static_index.html", dest / "index.html")
        print(f"dbt docs -> {dest}")


if __name__ == "__main__":
    main()
