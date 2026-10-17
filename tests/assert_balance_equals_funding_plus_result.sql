-- On every day, end-of-day balance = cumulative net funding + cumulative trading
-- result. Ties the daily balance fact back to the daily P&L fact.

select date_day, balance_usd, cumulative_net_funding_usd, cumulative_trading_result_usd
from {{ ref('fct_account_balance_daily') }}
where abs(balance_usd - (cumulative_net_funding_usd + cumulative_trading_result_usd)) > 0.005
