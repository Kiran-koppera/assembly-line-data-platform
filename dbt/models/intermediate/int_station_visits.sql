-- One row per vehicle and station: entry, exit and dwell time (work time plus any blocked time).
with ev as (
    select vin, station_id,
           min(event_ts) filter (where event_type = 'station_in')  as in_ts,
           min(event_ts) filter (where event_type = 'station_out') as out_ts,
           count(*) filter (where event_type = 'station_in')       as in_events,
           count(*) filter (where event_type = 'station_out')      as out_events
    from {{ ref('stg_station_events') }}
    group by vin, station_id
)
select
    ev.vin,
    ev.station_id,
    s.sequence,
    s.zone,
    ev.in_ts,
    ev.out_ts,
    extract(epoch from (ev.out_ts - ev.in_ts))::numeric(10, 1) as dwell_s,
    ev.in_events,
    ev.out_events
from ev
join {{ ref('dim_station') }} s using (station_id)
