-- Zone quality gates.
select
    event_id,
    event_ts,
    vin,
    station_id,
    payload ->> 'result'      as result,
    payload ->> 'defect_code' as defect_code
from {{ source('raw', 'events') }}
where event_type = 'quality_check'
