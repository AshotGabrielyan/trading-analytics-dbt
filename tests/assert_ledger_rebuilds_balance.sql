-- The cumulative sum of processed amounts, in booking order, must reproduce the
-- broker's running balance on every ledger row.

select fund_transaction_id, modified_at_utc, balance_usd, running_balance_usd
from {{ ref('fct_ledger_transactions') }}
where abs(balance_usd - running_balance_usd) > 0.005
