"""Line model settings. All data in this project is SIMULATED; these values are assumptions,
chosen to be consistent with public information and documented in docs/simulation.md.

Takt: Giga Berlin was reported at ~7,000 Model Y per week in October 2026 (public press). Over
~115 productive hours a week (3 shifts x 5 days, minus breaks) that is ~60 vehicles per hour,
i.e. a takt of about 60 seconds. The model uses exactly that as its target.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TAKT_S = 60.0                 # target seconds between vehicles leaving the line
SHIFT_STARTS_H = (6, 14, 22)  # three 8-hour shifts
BREAKS = [(10, 0, 30), (18, 0, 30), (2, 0, 30)]  # (hour, minute, minutes): releases pause
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Joint:
    joint_id: str
    target_nm: float
    tolerance_pct: float = 10.0


@dataclass(frozen=True)
class Station:
    station_id: str
    zone: str
    name: str
    base_cycle_s: float
    joints: tuple[Joint, ...] = ()
    quality_gate: bool = False
    eol_test: str | None = None


CYCLE_SCALE = 0.85  # station work content as a share of the listed times (balances the line below takt)


def _st(sid, zone, name, base, joints=(), gate=False, eol=None):
    return Station(sid, zone, name, round(base * CYCLE_SCALE, 1), tuple(joints), gate, eol)


J = Joint
STATIONS: list[Station] = [
    # Trim: interior before the body meets the chassis
    _st("T01", "Trim", "Door removal", 48),
    _st("T02", "Trim", "Wiring harness main", 54),
    _st("T03", "Trim", "Wiring harness rear", 52),
    _st("T04", "Trim", "Sound insulation", 47),
    _st("T05", "Trim", "Headliner", 50),
    _st("T06", "Trim", "Instrument panel install", 56, [J("T06-J1", 25), J("T06-J2", 25), J("T06-J3", 10)]),
    _st("T07", "Trim", "HVAC module", 51, [J("T07-J1", 9)]),
    _st("T08", "Trim", "Carpet and console", 49),
    _st("T09", "Trim", "Glass prep", 46),
    _st("T10", "Trim", "Windshield install", 57),
    _st("T11", "Trim", "Rear glass install", 53),
    _st("T12", "Trim", "Trim quality gate", 45, gate=True),
    # Chassis: drivetrain, battery pack and the "marriage" of body and chassis
    _st("C01", "Chassis", "Rear drive unit sub-assembly", 52, [J("C01-J1", 90), J("C01-J2", 90)]),
    _st("C02", "Chassis", "Front suspension", 53, [J("C02-J1", 120), J("C02-J2", 120)]),
    _st("C03", "Chassis", "Rear suspension", 54, [J("C03-J1", 120), J("C03-J2", 120)]),
    _st("C04", "Chassis", "Brake lines", 50, [J("C04-J1", 18)]),
    _st("C05", "Chassis", "Marriage: body to chassis", 58,
        [J("C05-J1", 180), J("C05-J2", 180), J("C05-J3", 180), J("C05-J4", 180)]),
    _st("C06", "Chassis", "Battery pack install", 57, [J("C06-J1", 60), J("C06-J2", 60), J("C06-J3", 60), J("C06-J4", 60)]),
    _st("C07", "Chassis", "Underbody shields", 47, [J("C07-J1", 8)]),
    _st("C08", "Chassis", "Exhaust-free cooling loop", 50, [J("C08-J1", 12)]),
    _st("C09", "Chassis", "Wheels and tyres", 55, [J("C09-J1", 175), J("C09-J2", 175)]),
    _st("C10", "Chassis", "Chassis quality gate", 45, gate=True),
    # Final: closures, seats, fluids
    _st("F01", "Final", "Doors re-hang", 56, [J("F01-J1", 30), J("F01-J2", 30)]),
    _st("F02", "Final", "Front seats", 52, [J("F02-J1", 45), J("F02-J2", 45)]),
    _st("F03", "Final", "Rear seats", 49, [J("F03-J1", 45)]),
    _st("F04", "Final", "Bumpers front", 50),
    _st("F05", "Final", "Bumpers rear", 50),
    _st("F06", "Final", "Lighting", 48),
    _st("F07", "Final", "Coolant and brake fill", 57),
    _st("F08", "Final", "Refrigerant fill", 54),
    _st("F09", "Final", "Washer fluid and 12V", 46),
    _st("F10", "Final", "Software flash", 55),
    _st("F11", "Final", "Interior finish", 47),
    _st("F12", "Final", "Final quality gate", 45, gate=True),
    # End of line test
    _st("E01", "EOL", "Wheel alignment", 56, eol="alignment"),
    _st("E02", "EOL", "Headlamp aim", 44, eol="headlamp"),
    _st("E03", "EOL", "Rolling road", 58, eol="dyno"),
    _st("E04", "EOL", "Water test", 55, eol="water"),
    _st("E05", "EOL", "ADAS calibration", 53, eol="adas"),
    _st("E06", "EOL", "Final inspection", 50, eol="final_inspection", gate=True),
]

# Per-station stoppages (andon): mean minutes between stoppages and mean duration.
ANDON_MTBF_MIN = 1200.0     # ~1.2 stoppages per station per day
ANDON_MTTR_MIN = 4.0
ANDON_REASONS = ["material_shortage", "tool_fault", "quality_hold", "safety_stop", "operator_call"]

# Process quality.
TORQUE_SIGMA_PCT = 2.4        # measurement spread around target, % of target
QUALITY_GATE_PASS = 0.985
EOL_FAIL_RATE = {"alignment": 0.012, "headlamp": 0.006, "dyno": 0.008, "water": 0.004, "adas": 0.010,
                 "final_inspection": 0.015}
CYCLE_SIGMA = 0.05            # lognormal spread of station cycle times


@dataclass
class RunConfig:
    start: str = "2026-11-16T06:00:00Z"
    days: float = 1.0
    seed: int = 42
    stations: list[Station] = field(default_factory=lambda: STATIONS)
