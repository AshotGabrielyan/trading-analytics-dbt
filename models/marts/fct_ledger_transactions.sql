-- Cash ledger fact: one row per processed cash movement, linked to the position
-- that produced it (TRADE rows), with a rebuilt running balance next to the
-- broker-reported one.

with ledger as (

    select * from {{ ref('int_ledger_transactions') }}

),

executions as (

    select exec_id, position_id
    from {{ ref('stg_trade_executions') }}

)

select
    ledger.fund_transaction_id,
    ledger.transaction_type,
    ledger.cash_flow_category,
    ledger.amount_usd,
    ledger.balance_usd,
    sum(ledger.amount_usd) over (
        order by ledger.modified_at_utc, ledger.fund_transaction_id
        rows between unbounded preceding and current row
    )                                               as running_balance_usd,
    ledger.exec_id,
    executions.position_id,
    ledger.instrument_symbol,
    ledger.modified_at_utc,
    ledger.transaction_date
from ledger
left join executions on ledger.exec_id = executions.exec_id
