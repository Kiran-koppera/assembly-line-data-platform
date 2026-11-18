-- PLC station entry and exit signals, one row per event.
select
    event_id,
    event_ts,
    event_type,
    vin,
    station_id
from {{ source('raw', 'events') }}
where event_type in ('station_in', 'station_out')
