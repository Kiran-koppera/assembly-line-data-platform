import copy
import json

from assembly.config import RunConfig
from assembly.ingest import ingest
from assembly.simulator import simulate, write_landing


def test_ingest_is_idempotent_and_handles_resends_bad_records_and_late_files(conn, tmp_path):
    events = simulate(RunConfig(days=0.1, seed=11))
    late = [e for e in events if e["ts"][11:13] == "07"]
    write_landing([e for e in events if e["ts"][11:13] != "07"], tmp_path)

    first = ingest(conn, tmp_path)
    assert first.loaded == len(events) - len(late) and first.quarantined == 0

    again = ingest(conn, tmp_path)                       # nothing changed: every file skipped
    assert again.files == 0 and again.loaded == 0 and again.skipped_files == first.files

    write_landing(late, tmp_path)                        # late hour arrives
    resend = copy.deepcopy(late[:20])                    # plus a network retry and two bad lines
    bad = ['{"not": "an event"}', "{broken json"]
    (tmp_path / "retry.jsonl").write_text("\n".join([json.dumps(e) for e in resend] + bad) + "\n")
    third = ingest(conn, tmp_path)
    assert third.loaded == len(late)
    assert third.duplicates == 20
    assert third.quarantined == 2

    total = conn.execute("SELECT count(*), count(DISTINCT event_id) FROM raw.events").fetchone()
    assert total[0] == total[1] == len(events)
    reasons = {r[0] for r in conn.execute("SELECT reason FROM raw.quarantine").fetchall()}
    assert reasons == {"invalid JSON", "missing or invalid field: event_id"}
