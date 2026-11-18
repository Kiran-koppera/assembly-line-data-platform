import json

import pytest

from assembly import benchmark, chaos, monitoring
from assembly.config import RunConfig
from assembly.pipeline import run_all
from assembly.simulator import simulate


@pytest.fixture()
def populated(tmp_path):
    """A fresh database loaded with half a simulated day, run through the whole pipeline."""
    return run_all(tmp_path / "landing", RunConfig(days=0.5, seed=5))


def test_clean_run_builds_models_and_raises_no_incidents(populated):
    assert populated["transform"]["tests_ok"], populated["transform"]["test_failures"]
    assert populated["incidents"] == []


def test_api_serves_kpis_from_the_same_data(populated):
    from fastapi.testclient import TestClient

    from assembly.api import app
    client = TestClient(app)
    assert client.get("/health").json()["events"] > 0
    summary = client.get("/kpis/summary").json()
    assert isinstance(summary["vehicles"], int) and summary["vehicles"] > 0      # numbers, not strings
    assert isinstance(summary["first_pass_yield"], float) and 0 < summary["first_pass_yield"] <= 1
    assert client.get("/vehicles/NOPE").status_code == 404


def test_benchmark_reports_every_query(populated, tmp_path):
    from assembly import db
    with db.connect() as conn:
        out = benchmark.run(conn, tmp_path / "bench.json", runs=1)
    assert {q["query"] for q in out["queries"]} == set(benchmark.QUERIES)
    assert json.loads((tmp_path / "bench.json").read_text())["rows"] > 0


def test_drills_detect_faults_without_false_alarms(tmp_path):
    clean = simulate(RunConfig(days=0.75, seed=9))
    picks = {s.name: s for s in chaos.SCENARIOS}
    for name in ("baseline", "clock_drift", "schema_drift", "station_dropout"):
        result = chaos.run_drill(picks[name], clean, tmp_path)
        assert result["passed"], result


def test_incidents_collapse_to_a_few_per_check():
    many = [monitoring.Incident("clock_skew", "critical", f"s{i}") for i in range(9)]
    out = monitoring._collapse(many, keep=5)
    assert len(out) == 6 and out[-1].summary.startswith("... and 4 more")


def test_export_writes_dashboard_and_data(populated, tmp_path):
    from assembly.export import export
    counts = export(tmp_path / "site")
    assert (tmp_path / "site" / "index.html").exists()
    assert counts["throughput"] > 0 and counts["stations"] > 0
    meta = json.loads((tmp_path / "site" / "data" / "meta.json").read_text())
    assert meta[0]["events"] > 0
