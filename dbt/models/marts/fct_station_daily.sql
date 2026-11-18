-- Per station and day: vehicles, dwell-time percentiles, share over takt and stoppage minutes.
with v as (
    select station_id, in_ts::date as day, count(*) as vehicles,
           percentile_cont(0.5)  within group (order by dwell_s) as p50_dwell_s,
           percentile_cont(0.95) within group (order by dwell_s) as p95_dwell_s,
           avg((dwell_s > s.takt_s)::int)                         as share_over_takt
    from {{ ref('int_station_visits') }} iv
    join {{ ref('dim_station') }} s using (station_id)
    where dwell_s is not null
    group by station_id, in_ts::date
),
a as (
    select station_id, start_ts::date as day, count(*) as stoppages, round(sum(duration_min)::numeric, 1) as stoppage_min
    from {{ ref('int_andon_intervals') }}
    where end_ts is not null
    group by station_id, start_ts::date
)
select
    v.station_id, s.zone, s.station_name, v.day, v.vehicles,
    round(v.p50_dwell_s::numeric, 1) as p50_dwell_s,
    round(v.p95_dwell_s::numeric, 1) as p95_dwell_s,
    round(v.share_over_takt::numeric, 4) as share_over_takt,
    coalesce(a.stoppages, 0) as stoppages,
    coalesce(a.stoppage_min, 0) as stoppage_min
from v
join {{ ref('dim_station') }} s using (station_id)
left join a using (station_id, day)
