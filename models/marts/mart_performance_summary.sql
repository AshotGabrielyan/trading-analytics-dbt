-- Whole-account headline KPIs in a single row: trading performance (same metric
-- definitions as the per-instrument mart), cash flows and drawdown.

with positions as (

    select * from {{ ref('fct_positions') }}

),

trading as (

    select
        {{ position_performance_metrics() }},
        min(opened_at_utc)      as first_opened_at_utc,
        max(closed_at_utc)      as last_closed_at_utc,
        count(distinct instrument_symbol) as n_instruments
    from positions

),

cash as (

    select
        sum(case when transaction_type = 'DEPOSIT' then amount_usd end)     as total_deposits_usd,
        sum(case when transaction_type = 'WITHDRAWAL' then amount_usd end)  as total_withdrawals_usd,
        sum(case when cash_flow_category = 'rebate' then amount_usd end)    as total_rebates_usd,
        sum(case
                when cash_flow_category = 'adjustment'
                 and transaction_type <> 'CASH_ADJUSTMENT_COMMODITIES'
                then amount_usd
            end)                                                            as total_account_adjustments_usd,
        arg_max(balance_usd, modified_at_utc)                           as ending_balance_usd
    from {{ ref('fct_ledger_transactions') }}

),

drawdown as (

    select
        min(drawdown_usd)                       as max_drawdown_usd,
        max(peak_trading_result_usd)            as peak_trading_result_usd
    from {{ ref('fct_account_balance_daily') }}

)

select
    trading.*,
    cash.total_deposits_usd,
    cash.total_withdrawals_usd,
    cash.total_rebates_usd,
    cash.total_account_adjustments_usd,
    cash.ending_balance_usd,
    drawdown.max_drawdown_usd,
    drawdown.peak_trading_result_usd
from trading
cross join cash
cross join drawdown
