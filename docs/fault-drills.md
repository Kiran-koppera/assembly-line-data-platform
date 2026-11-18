# Fault drills and postmortems

`python -m assembly drills` starts from one clean simulated day, injects one fault per scenario
the way it happens in a plant, runs the whole pipeline on a fresh database and records which
checks fire. A drill passes when the expected check fires and **no unrelated critical check does**.
The deploy workflow runs all drills on every push and fails the build if one is missed.

## Results

| Scenario | Injected fault | Caught by | Finding |
|---|---|---|---|
| baseline | none | nothing (as expected) | 0 incidents, 0 dbt test failures |
| clock_drift | F07's PLC clock jumps 3 min ahead at 10:00 | `clock_skew` | F07: median transfer +180 s; F08: −180 s |
| resend_burst | Torque gateway re-sends 500 events (same ids) | `resent_events` | 500 re-sent events ignored by idempotent load |
| duplicate_new_ids | PLC restart replays an hour of C03 entries with new ids | `duplicate_station_events` | 51 vehicles reported more than once at C03 |
| station_dropout | C04 stops reporting 12:00–13:00 | `missing_station_records`, `station_silence`, dbt `completed_vehicles_visit_every_station` | 59 completed vehicles have no record at C04 |
| unit_change | C05 torque tool reports lbf·ft from 14:00 | `torque_level_shift` | C05-J1 at 14:00: median 0.73 × target |
| schema_drift | C06 firmware renames `torque_nm` to `torque_value` | `contract_violations` | 240 records quarantined |
| late_arrival | 03:00–04:00 files arrive six hours late | `late_arrivals` | 6,051 events arrived late; models rebuilt |

**8 of 8 pass: 7 of 7 faults detected, 0 false alarms.**

## Postmortems

### Clock drift at F07
- **Impact if missed:** F07 dwell times stay plausible, but every vehicle appears to reach F08
  three minutes *before* leaving F07. Station-to-station flow and bottleneck analysis are wrong.
- **Detection:** median transfer time into a station should be ~0 s on a synchronous conveyor;
  F07 shows +180 s and F08 −180 s, which points at F07's clock, not F08's.
- **Fix:** resync the PLC clock (NTP), then correct the affected window or flag it in the marts.
- **Prevention:** keep the clock-skew check on every load; alert the controls team on first hit.

### Duplicate entries after a PLC restart (new event ids)
- **Impact if missed:** vehicles counted twice at C03; per-station volumes and dwell times inflate.
- **Detection:** the primary key cannot help (new ids), so a natural-key check (vehicle, station,
  event type) catches it.
- **Prevention:** ask the PLC integration for idempotent event ids derived from vehicle and station.

### Station dropout at C04
- **Impact if missed:** C04 looks idle for an hour while 59 vehicles passed through it; any KPI by
  station undercounts, and traceability for those vehicles has a gap.
- **Detection:** three independent signals: completed vehicles without a C04 record, C04 silent
  while C03 kept handing over vehicles, and the dbt completeness test.
- **Fix:** replay the gateway buffer for C04 if available; otherwise mark the window as missing.

### Torque unit change at C05
- **Impact if missed:** values stay inside physical limits (~133 instead of 180), so range checks
  pass, but every reading is off by the lbf·ft factor and capability metrics collapse.
- **Detection:** hourly median reading per joint versus its target (0.73 × instead of ~1.0).
- **Prevention:** add the unit to the data contract and reject unknown units at ingestion.

### Schema drift at C06
- **Impact if missed:** a silent null in torque analytics for C06 joints.
- **Detection:** the data contract rejects the record; it lands in `raw.quarantine` with the reason,
  so nothing is lost and it can be replayed after a mapping fix.

### Re-sent events and late files
- Handled by design: the primary key drops exact re-sends, and file checksums plus partition
  creation on demand load late files into the right day. Both are reported as warnings so the
  source can be fixed, and models are rebuilt from raw.
