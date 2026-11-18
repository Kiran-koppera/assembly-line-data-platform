-- Process capability per joint and day (first attempts only). Cpk >= 1.33 is a common target.
select
    joint_id, station_id, event_ts::date as day,
    count(*) as tightenings,
    round(avg(torque_nm), 2) as mean_nm,
    round(stddev_samp(torque_nm), 3) as std_nm,
    max(target_nm) as target_nm,
    round(least(max(upper_nm) - avg(torque_nm), avg(torque_nm) - max(lower_nm)) / nullif(3 * stddev_samp(torque_nm), 0), 2) as cpk,
    round(avg((result = 'NOK')::int), 4) as nok_rate
from {{ ref('stg_torque_results') }}
where attempt = 1
group by joint_id, station_id, event_ts::date
