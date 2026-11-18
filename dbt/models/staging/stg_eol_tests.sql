-- End-of-line tests and post-rework retests.
select
    event_id,
    event_ts,
    event_type,
    vin,
    station_id,
    payload ->> 'test'   as test_name,
    payload ->> 'result' as result,
    event_type = 'eol_retest' as is_retest
from {{ source('raw', 'events') }}
where event_type in ('eol_test', 'eol_retest')
