from collections import Counter

from assembly.config import STATIONS, RunConfig
from assembly.contract import validate
from assembly.simulator import simulate

SMALL = RunConfig(days=0.25, seed=7)


def test_simulation_is_deterministic():
    a, b = simulate(SMALL), simulate(SMALL)
    assert len(a) == len(b) and a[0] == b[0] and a[-1] == b[-1]


def test_every_event_meets_the_contract():
    events = simulate(SMALL)
    assert all(validate(e) is None for e in events)


def test_completed_vehicles_pass_every_station_once():
    events = simulate(SMALL)
    done = {e["vin"] for e in events if e["event_type"] == "station_out" and e["station_id"] == STATIONS[-1].station_id}
    ins = Counter(e["vin"] for e in events if e["event_type"] == "station_in" and e["vin"] in done)
    assert done and set(ins.values()) == {len(STATIONS)}


def test_line_runs_near_takt():
    events = simulate(RunConfig(days=0.25, seed=3))
    done = [e for e in events if e["event_type"] == "station_out" and e["station_id"] == "E06"]
    # 6 h at 60 s takt = 360 vehicles at most; the first vehicle needs ~35 min to cross 40 stations
    assert 250 <= len(done) <= 360


def _ok():
    return {"event_id": "x", "schema_version": "1.0", "source": "torque", "event_type": "torque_result",
            "ts": "2026-11-16T06:00:00.000Z", "vin": "SIM1", "station_id": "C05", "joint_id": "C05-J1",
            "torque_nm": 180.0, "target_nm": 180, "lower_nm": 162, "upper_nm": 198, "attempt": 1, "result": "OK"}


def test_contract_accepts_valid_event():
    assert validate(_ok()) is None


def test_contract_rejects_renamed_field():
    e = _ok()
    e["torque_value"] = e.pop("torque_nm")
    assert "torque_nm" in validate(e)


def test_contract_rejects_bad_types_station_and_time():
    assert "attempt" in validate({**_ok(), "attempt": True})          # bool is not an int here
    assert "unknown station_id" in validate({**_ok(), "station_id": "Z99"})
    assert "ts" in validate({**_ok(), "ts": "yesterday"})
    assert "schema_version" in validate({**_ok(), "schema_version": "2.0"})
    assert "unknown event_type" in validate({**_ok(), "event_type": "teleport"})
