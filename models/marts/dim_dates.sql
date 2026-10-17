-- Calendar spine, one row per day from the first account event (var
-- `calendar_start_date`) through today, so daily facts have a row for every
-- day, including days with no trading.

with spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('" ~ var('calendar_start_date') ~ "' as date)",
        end_date="(current_date + 1)"
    ) }}

)

select
    cast(date_day as date)                                  as date_day,
    cast(date_trunc('week', date_day) as date)              as week_start_date,
    cast(date_trunc('month', date_day) as date)             as month_start_date,
    year(date_day)                                          as year_number,
    month(date_day)                                         as month_number,
    isodow(date_day)                                        as iso_day_of_week,
    dayname(date_day)                                       as day_name,
    isodow(date_day) in (6, 7)                              as is_weekend
from spine
