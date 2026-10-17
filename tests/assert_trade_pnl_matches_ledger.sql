-- Realized P&L on CLOSED executions must equal the TRADE cash movements in the
-- processed ledger. Returns a row (= failure) if they differ by more than a cent.

with executions as (
    select sum(realized_pnl_usd) as pnl_usd
    from {{ ref('stg_trade_executions') }}
    where execution_status = 'CLOSED'
),

ledger as (
    select sum(amount_usd) as pnl_usd
    from {{ ref('int_ledger_transactions') }}
    where transaction_type = 'TRADE'
)

select executions.pnl_usd as executions_pnl_usd, ledger.pnl_usd as ledger_pnl_usd
from executions cross join ledger
where abs(executions.pnl_usd - ledger.pnl_usd) > 0.005
