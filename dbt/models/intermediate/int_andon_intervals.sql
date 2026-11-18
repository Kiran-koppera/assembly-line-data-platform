-- Stoppages as intervals (start and end paired by andon_id).
select
    andon_id,
    station_id,
    max(reason) as reason,
    min(event_ts) filter (where event_type = 'andon_start') as start_ts,
    min(event_ts) filter (where event_type = 'andon_end')   as end_ts,
    extract(epoch from (min(event_ts) filter (where event_type = 'andon_end')
                      - min(event_ts) filter (where event_type = 'andon_start'))) / 60.0 as duration_min
from {{ ref('stg_andon_events') }}
group by andon_id, station_id
