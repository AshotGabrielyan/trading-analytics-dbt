-- Trade performance KPIs per instrument (win rate, profit factor, expectancy,
-- exit mix, long vs short). Metric definitions live in the
-- position_performance_metrics macro.

with positions as (

    select * from {{ ref('fct_positions') }}

)

select
    instrument_symbol,
    asset_class,
    {{ position_performance_metrics() }},
    min(opened_at_utc)      as first_opened_at_utc,
    max(closed_at_utc)      as last_closed_at_utc
from positions
group by 1, 2
