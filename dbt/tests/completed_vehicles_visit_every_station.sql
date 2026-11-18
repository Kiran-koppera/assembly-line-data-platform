-- A vehicle that left the line must have a record at every station.
select vin, stations_reported
from {{ ref('int_vehicle_journey') }}
where line_exit_ts is not null
  and stations_reported < (select count(*) from {{ ref('dim_station') }})
