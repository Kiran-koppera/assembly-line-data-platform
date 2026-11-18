-- Torque tool results: one row per tightening attempt.
select
    event_id,
    event_ts,
    vin,
    station_id,
    payload ->> 'joint_id'              as joint_id,
    (payload ->> 'torque_nm')::numeric  as torque_nm,
    (payload ->> 'target_nm')::numeric  as target_nm,
    (payload ->> 'lower_nm')::numeric   as lower_nm,
    (payload ->> 'upper_nm')::numeric   as upper_nm,
    (payload ->> 'attempt')::int        as attempt,
    payload ->> 'result'                as result
from {{ source('raw', 'events') }}
where event_type = 'torque_result'
