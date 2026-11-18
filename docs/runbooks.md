# Runbooks

One entry per monitoring check: what it means, how to confirm it, what to do. Queries run against
the platform database (`raw`, `intermediate`, `marts`, `monitoring` schemas).

## contract_violations (critical)
Records failed the data contract and were quarantined.
```sql
SELECT reason, count(*), min(file_path) FROM raw.quarantine GROUP BY reason ORDER BY 2 DESC;
```
Look at `raw_line` for the first examples. A renamed field usually means a firmware or integration
change: agree the mapping with the source owner, update `contract.py` with a new `schema_version`,
then replay the quarantined lines.

## resent_events (warning)
Exact re-sends dropped by the primary key. No data impact; repeated bursts point to retries at the
gateway. Check `ops.ingest_batches.duplicates` over time.

## duplicate_station_events (critical)
A vehicle reported more than once at a station under different event ids.
```sql
SELECT * FROM intermediate.int_station_visits WHERE in_events > 1 OR out_events > 1 ORDER BY in_ts;
```
Typical cause: PLC restart replaying its buffer. Exclude the duplicates in staging (keep the first
by `event_ts`) and ask for deterministic event ids.

## clock_skew (critical)
A station's timestamps are offset from its neighbours. The station with the positive median
transfer time is usually the one whose clock is ahead; the next station shows the negative mirror.
Resync the device clock, then decide with the plant team whether to correct or flag the window.

## missing_station_records / station_silence (critical)
Vehicles passed a station that did not report. Confirm the window:
```sql
SELECT date_trunc('minute', event_ts), count(*) FROM raw.events
WHERE station_id = 'C04' AND event_type = 'station_in' GROUP BY 1 ORDER BY 1;
```
Check the station's gateway and network; replay its buffer if it has one.

## torque_level_shift (critical)
A joint's hourly median moved away from its target. A ratio near 0.74 or 1.36 suggests a
lbf·ft / N·m mix-up; other shifts can be a real process problem (tool calibration). Involve the
quality engineer before correcting any data.

## late_arrivals (warning)
Files arrived hours after their events. Data is loaded into the right day and models are rebuilt,
so KPIs are correct after the next run. Repeated late arrivals point to a gateway backlog.
