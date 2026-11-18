# Simulation model

**All data in this project is simulated.** No real factory data is used, and the model is not
affiliated with any manufacturer. The line is modelled on public information about how a modern
general-assembly (GA) shop works, so the pipeline faces realistic volumes, timing and faults.

## The line

40 stations in four zones, each holding one vehicle at a time (SimPy discrete-event model):

| Zone | Stations | What happens |
|---|---|---|
| Trim | T01–T12 | Wiring, insulation, headliner, instrument panel, glass |
| Chassis | C01–C10 | Drive unit, suspension, **marriage of body and chassis (C05)**, battery pack (C06), wheels |
| Final | F01–F12 | Doors, seats, fluids, software flash |
| End of line | E01–E06 | Alignment, headlamp aim, rolling road, water test, ADAS calibration, final inspection |

A vehicle only leaves a station when the next one is free (blocking), so a slow station or a
stoppage backs up the line the way a conveyor does.

## Settings and where they come from

| Setting | Value | Basis |
|---|---|---|
| Takt | 60 s (target 60 vehicles/hour) | Giga Berlin was publicly reported at ~7,000 Model Y in a week (Oct 2026); over ~115 productive hours that is ~60 per hour |
| Shifts and breaks | 3 × 8 h, a 30-min break per shift | Common three-shift pattern; releases pause during breaks |
| Station work content | 37–49 s (85 % of the listed base times) | Balanced below takt, as lines are |
| Cycle-time spread | lognormal, σ = 0.05 | Assumption |
| Stoppages (andon) | 1 per station every ~20 h, mean 4 min | Assumption; gives about 200–215 stoppage minutes per full day across all 40 stations |
| Torque spread | σ = 2.4 % of target, tolerance ±10 % | Gives Cpk ≈ 1.4, around the common 1.33 minimum |
| Quality gates | 98.5 % pass | Assumption |
| End-of-line test failures | 0.4–1.5 % per test, then off-line rework and retest | Assumption; gives ~95 % first-pass yield |

## Result on a 3-day run

457,990 events, 3,910 vehicles, a median of 58 vehicles per hour in production hours, first-pass
yield 94–95 %. About 152,000 events per full day.

## Events

Each event has an envelope (`event_id`, `schema_version`, `source`, `event_type`, `ts`, `vin`,
`station_id`) and type-specific fields. Sources: `plc` (station in/out), `torque` (tool results),
`andon` (stoppages), `quality` (zone gates), `eol` (tests and retests). Files land hourly as
`landing/date=YYYY-MM-DD/hour=HH/<source>.jsonl`, like files dropped by an edge gateway. The data
contract is in [`src/assembly/contract.py`](../src/assembly/contract.py).

Public sources for the takt assumption: Drive Tesla Canada, "Tesla Giga Berlin 7,000 Model Y week";
Electrive, "Tesla plans another 1,000 hires in Grünheide" (June 2026).
