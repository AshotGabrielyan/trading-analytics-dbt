-- One row per execution event on a CFD position (open, close, SL/TP modify, swap).
-- Source arrives as text; this model only casts, renames and drops constant columns.

with source as (

    select * from {{ source('broker', 'leveraged_trades') }}

),

renamed as (

    select
        "Exec Id"                                       as exec_id,
        "Trade Id"                                      as position_id,
        nullif("Order Id", '')                          as order_id,

        "Instrument Symbol"                             as instrument_symbol,
        "Instrument Name"                               as instrument_name,
        "Currency"                                      as instrument_currency,

        "Status"                                        as execution_status,
        "Source"                                        as execution_source,
        nullif("Execution Type", '')                    as order_type,

        cast("Quantity" as decimal(18, 4))              as quantity,
        case
            when cast("Quantity" as decimal(18, 4)) > 0 then 'long'
            when cast("Quantity" as decimal(18, 4)) < 0 then 'short'
        end                                             as quantity_direction,
        cast(nullif("Price", '') as decimal(18, 6))       as price,
        cast(nullif("Take Profit", '') as decimal(18, 6)) as take_profit,
        cast(nullif("Stop Loss", '') as decimal(18, 6))   as stop_loss,

        -- rpl is in instrument currency; *_converted is in account currency (USD)
        cast(nullif("rpl", '') as decimal(18, 2))            as realized_pnl_local,
        cast(nullif("Rpl Converted", '') as decimal(18, 2))  as realized_pnl_usd,
        cast(nullif("Swap", '') as decimal(18, 2))           as swap_local,
        cast(nullif("Swap Converted", '') as decimal(18, 2)) as swap_usd,

        {{ parse_broker_timestamp('"Timestamp (UTC)"') }} as executed_at_utc

        -- dropped: Account Id (identifier), Account type (always CFD),
        --          Fee (always 0), gsl (always false)

    from source

)

select * from renamed
