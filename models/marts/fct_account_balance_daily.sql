-- End-of-day account balance for every calendar day, with cumulative funding,
-- cumulative trading result and drawdown of the trading result from its peak.
-- Balance is carried forward over days with no ledger activity.

with daily as (

    select * from {{ ref('fct_daily_pnl') }}

),

end_of_day_balance as (

    select
        transaction_date                                    as date_day,
        arg_max(balance_usd, modified_at_utc)               as balance_usd
    from {{ ref('fct_ledger_transactions') }}
    group by 1

),

with_balance as (

    select
        daily.date_day,
        -- last known balance (ignore nulls = carry forward)
        last_value(end_of_day_balance.balance_usd ignore nulls)
            over (order by daily.date_day rows between unbounded preceding and current row)
                                                                as balance_usd,
        sum(daily.deposits_usd + daily.withdrawals_usd)
            over (order by daily.date_day)                      as cumulative_net_funding_usd,
        daily.cumulative_trading_result_usd
    from daily
    left join end_of_day_balance on daily.date_day = end_of_day_balance.date_day

)

select
    date_day,
    coalesce(balance_usd, 0)                                    as balance_usd,
    cumulative_net_funding_usd,
    cumulative_trading_result_usd,
    max(cumulative_trading_result_usd) over (order by date_day) as peak_trading_result_usd,
    cumulative_trading_result_usd
        - max(cumulative_trading_result_usd) over (order by date_day)
                                                                as drawdown_usd
from with_balance
