-- Vehicles leaving the line per hour against the takt target (60 per hour at 60 s takt).
with done as (
    select date_trunc('hour', line_exit_ts) as hour, count(*) as vehicles
    from {{ ref('int_vehicle_journey') }}
    where line_exit_ts is not null
    group by 1
)
select
    hour,
    vehicles,
    (3600 / (select max(takt_s) from {{ ref('dim_station') }}))::int as target,
    round(vehicles / (3600 / (select max(takt_s) from {{ ref('dim_station') }})), 3) as attainment
from done
order by hour
