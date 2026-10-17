-- Swaps attributed to positions (from SWAP executions) must equal the SWAP
-- cash movements in the ledger.

with positions as (
    select sum(swap_usd) as swap_usd from {{ ref('fct_positions') }}
),

ledger as (
    select sum(amount_usd) as swap_usd
    from {{ ref('int_ledger_transactions') }}
    where transaction_type = 'SWAP'
)

select positions.swap_usd as positions_swap_usd, ledger.swap_usd as ledger_swap_usd
from positions cross join ledger
where abs(positions.swap_usd - ledger.swap_usd) > 0.005
