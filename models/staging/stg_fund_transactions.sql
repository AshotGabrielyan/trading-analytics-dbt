-- One row per cash movement on the account ledger, with the broker's running balance.
-- Each ledger row is kept once (from the latest export). DECLINED rows are kept and
-- flagged so nothing is silently dropped here.

with source as (

    select * from {{ source('broker', 'funds_history') }}

),

deduplicated as (

    {{ latest_export_rows('source', '"Id"') }}

),

renamed as (

    select
        "Id"                                        as fund_transaction_id,
        "Type"                                      as transaction_type,
        "Status"                                    as transaction_status,
        "Status" = 'PROCESSED'                      as is_processed,

        cast("Amount" as decimal(18, 2))            as amount_usd,
        cast("Balance" as decimal(18, 2))           as balance_usd,
        "Currency"                                  as currency,

        -- "Trade Id" is "<exec id>_<suffix>" on TRADE rows; the prefix joins to trade executions
        nullif("Trade Id", '')                      as broker_trade_ref,
        nullif(split_part("Trade Id", '_', 1), '')  as exec_id,

        nullif("Instrument Symbol", '')             as instrument_symbol,

        {{ parse_broker_timestamp('"Modified (UTC)"') }} as modified_at_utc

        -- dropped: Quantity, Regulatory fees, Taxes (always empty), Commission (always 0 or empty), ISIN (always '-'),
        --          Instrument Name (available on executions), Account type (always CFD)

    from deduplicated

)

select * from renamed
