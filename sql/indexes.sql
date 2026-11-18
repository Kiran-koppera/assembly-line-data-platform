-- Secondary indexes on raw.events, chosen from the benchmark in docs/benchmarks.md.
-- Defined on the partitioned parent, so every daily partition gets them automatically.

-- Station and event-type lookups within a time window (throughput, dwell time).
CREATE INDEX IF NOT EXISTS events_station_type_ts_idx ON raw.events (station_id, event_type, event_ts);

-- Troubleshooting a single vehicle.
CREATE INDEX IF NOT EXISTS events_vin_idx ON raw.events (vin, event_ts);

-- Torque analysis by joint: an expression index on the JSON field, only for torque events.
CREATE INDEX IF NOT EXISTS events_torque_joint_idx ON raw.events ((payload ->> 'joint_id'))
    WHERE event_type = 'torque_result';
