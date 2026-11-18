# SQL optimization benchmark

`python -m assembly bench --days 7` loads one simulated week (1,056,518 events) into
`raw.events`, then times four everyday queries with `EXPLAIN (ANALYZE)`: the median of 7 runs
after a warm-up, first without secondary indexes and then with the indexes in
[`sql/indexes.sql`](../sql/indexes.sql). Measured locally on a laptop (Apple Silicon, embedded
PostgreSQL 16.2). Absolute times depend on the machine; the plan change is what matters.

| Query | Before | Plan | After | Plan | Speed-up |
|---|---|---|---|---|---|
| Hourly throughput, one day | 4.13 ms | Seq Scan | 0.39 ms | Bitmap Heap Scan | 10.6× |
| Station dwell p50/p95, one day | 5.26 ms | Seq Scan | 0.85 ms | Bitmap Heap Scan | 6.2× |
| Torque joint statistics, whole week | 30.95 ms | Seq Scan | 3.92 ms | Bitmap Heap Scan | 7.9× |
| Vehicle history lookup | 26.30 ms | Seq Scan | 0.03 ms | Index Scan | 876.7× |

## What each index does

- **`(station_id, event_type, event_ts)`**: throughput and dwell queries filter on all three; the
  daily partitions already prune by time, the index narrows to one station and event type.
- **`(vin, event_ts)`**: troubleshooting starts from a vehicle; without it every partition is scanned.
- **Partial expression index on `payload->>'joint_id'` for torque events only**: keeps the JSON
  payload flexible while making joint analysis cheap, and the index stays small because it only
  covers torque rows.

## Trade-off

Indexes slow ingestion: the full week loads in about 10 seconds without them and 13 seconds with them. Dashboard and
troubleshooting queries run far more often than loads, so read speed wins.
Full results: [`output/benchmarks.json`](../output/benchmarks.json).
