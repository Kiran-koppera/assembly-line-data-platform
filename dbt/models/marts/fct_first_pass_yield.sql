-- End-of-line first-pass yield: share of tested vehicles that passed every test the first time.
with t as (
    select vin, min(event_ts)::date as day, bool_and(result = 'pass') as passed_first_time
    from {{ ref('stg_eol_tests') }}
    where not is_retest
    group by vin
)
select day, count(*) as vehicles_tested,
       count(*) filter (where passed_first_time) as passed_first_time,
       round(avg(passed_first_time::int), 4) as first_pass_yield
from t
group by day
order by day
