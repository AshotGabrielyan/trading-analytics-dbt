-- Processed cash movements only (DECLINED rows never hit the balance),
-- grouped into analysis-friendly categories.

with fund_transactions as (

    select * from {{ ref('stg_fund_transactions') }}
    where is_processed

)

select
    fund_transaction_id,
    transaction_type,
    case transaction_type
        when 'DEPOSIT'                     then 'funding'
        when 'WITHDRAWAL'                  then 'funding'
        when 'TRADE'                       then 'trading_pnl'
        when 'SWAP'                        then 'financing'
        when 'REBATE'                      then 'rebate'
        when 'NEGATIVE_BALANCE_PROTECTION' then 'adjustment'
        when 'CASH_ADJUSTMENT_COMMODITIES' then 'adjustment'
        when 'TRADE_CORRECTION'            then 'adjustment'
    end                                         as cash_flow_category,
    amount_usd,
    balance_usd,
    exec_id,
    instrument_symbol,
    modified_at_utc,
    cast(modified_at_utc as date)               as transaction_date
from fund_transactions
