-- One row per calendar day: cash flows by category (from the ledger, so it
-- reconciles to the balance) plus trading activity (positions closed that day).

with dates as (

    select date_day from {{ ref('dim_dates') }}

),

daily_cash as (

    select
        transaction_date                                                            as date_day,
        sum(case when cash_flow_category = 'trading_pnl' then amount_usd end)       as realized_pnl_usd,
        sum(case when cash_flow_category = 'financing' then amount_usd end)         as swap_usd,
        sum(case when cash_flow_category = 'rebate' then amount_usd end)            as rebate_usd,
        sum(case when cash_flow_category = 'adjustment' then amount_usd end)        as adjustment_usd,
        sum(case when transaction_type = 'DEPOSIT' then amount_usd end)             as deposits_usd,
        sum(case when transaction_type = 'WITHDRAWAL' then amount_usd end)          as withdrawals_usd
    from {{ ref('int_ledger_transactions') }}
    group by 1

),

daily_positions as (

    select
        closed_date                                 as date_day,
        count(*)                                    as n_positions_closed,
        count(case when outcome = 'win' then 1 end)     as n_wins,
        count(case when outcome = 'loss' then 1 end)    as n_losses
    from {{ ref('fct_positions') }}
    group by 1

),

joined as (

    select
        dates.date_day,
        coalesce(daily_cash.realized_pnl_usd, 0)    as realized_pnl_usd,
        coalesce(daily_cash.swap_usd, 0)            as swap_usd,
        coalesce(daily_cash.rebate_usd, 0)          as rebate_usd,
        coalesce(daily_cash.adjustment_usd, 0)      as adjustment_usd,
        coalesce(daily_cash.deposits_usd, 0)        as deposits_usd,
        coalesce(daily_cash.withdrawals_usd, 0)     as withdrawals_usd,
        coalesce(daily_positions.n_positions_closed, 0) as n_positions_closed,
        coalesce(daily_positions.n_wins, 0)         as n_wins,
        coalesce(daily_positions.n_losses, 0)       as n_losses
    from dates
    left join daily_cash on dates.date_day = daily_cash.date_day
    left join daily_positions on dates.date_day = daily_positions.date_day

)

select
    *,
    -- everything that is not funding: the account's trading result for the day
    realized_pnl_usd + swap_usd + rebate_usd + adjustment_usd   as net_trading_result_usd,
    sum(realized_pnl_usd + swap_usd + rebate_usd + adjustment_usd)
        over (order by date_day)                                 as cumulative_trading_result_usd
from joined
