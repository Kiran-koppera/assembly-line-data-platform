"""Data contract for line events (schema_version 1.0).

Every event needs the envelope fields; each event type needs its own payload fields with the
right types. A record that breaks the contract goes to raw.quarantine with the reason.
"""
from __future__ import annotations

from datetime import datetime

from .config import SCHEMA_VERSION, STATIONS

ENVELOPE = {"event_id": str, "schema_version": str, "source": str, "event_type": str, "ts": str}
STATION_IDS = {s.station_id for s in STATIONS}
NUM = (int, float)

PAYLOAD = {
    "station_in": {"vin": str, "station_id": str},
    "station_out": {"vin": str, "station_id": str},
    "torque_result": {"vin": str, "station_id": str, "joint_id": str, "torque_nm": NUM, "target_nm": NUM,
                      "lower_nm": NUM, "upper_nm": NUM, "attempt": int, "result": str},
    "andon_start": {"station_id": str, "andon_id": str, "reason": str},
    "andon_end": {"station_id": str, "andon_id": str, "reason": str},
    "quality_check": {"vin": str, "station_id": str, "result": str},
    "eol_test": {"vin": str, "station_id": str, "test": str, "result": str},
    "eol_retest": {"vin": str, "station_id": str, "test": str, "result": str},
}
ENVELOPE_KEYS = set(ENVELOPE) | {"vin", "station_id"}


def validate(e: dict) -> str | None:
    """Return None if the event is valid, else a short reason."""
    for k, t in ENVELOPE.items():
        if not isinstance(e.get(k), t):
            return f"missing or invalid field: {k}"
    if e["schema_version"] != SCHEMA_VERSION:
        return f"unsupported schema_version {e['schema_version']}"
    spec = PAYLOAD.get(e["event_type"])
    if spec is None:
        return f"unknown event_type {e['event_type']}"
    for k, t in spec.items():
        v = e.get(k)
        if isinstance(v, bool) or not isinstance(v, t):
            return f"{e['event_type']}: missing or invalid field {k}"
    if e.get("station_id") is not None and e["station_id"] not in STATION_IDS:
        return f"unknown station_id {e['station_id']}"
    try:
        datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
    except ValueError:
        return "unparseable ts"
    return None


def payload(e: dict) -> dict:
    return {k: v for k, v in e.items() if k not in ENVELOPE_KEYS}
