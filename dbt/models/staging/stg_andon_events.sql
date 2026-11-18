-- Line stoppage calls (andon) with reason codes.
select
    event_id,
    event_ts,
    event_type,
    station_id,
    payload ->> 'andon_id' as andon_id,
    payload ->> 'reason'   as reason
from {{ source('raw', 'events') }}
where event_type in ('andon_start', 'andon_end')
