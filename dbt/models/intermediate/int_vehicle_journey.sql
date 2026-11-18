-- One row per vehicle: when it entered and left the line, and how many stations reported it.
select
    vin,
    min(in_ts)  filter (where sequence = 1)                                         as line_entry_ts,
    max(out_ts) filter (where sequence = (select max(sequence) from {{ ref('dim_station') }})) as line_exit_ts,
    count(*)                                                                        as stations_reported,
    count(*) filter (where out_ts is not null)                                      as stations_completed
from {{ ref('int_station_visits') }}
group by vin
