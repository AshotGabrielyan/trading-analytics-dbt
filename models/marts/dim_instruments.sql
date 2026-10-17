-- One row per traded instrument, with its asset class and trading activity window.

with executions as (

    select * from {{ ref('stg_trade_executions') }}

),

instruments as (

    select
        instrument_symbol,
        any_value(instrument_name)          as instrument_name,
        any_value(instrument_currency)      as instrument_currency,
        min(executed_at_utc)                as first_traded_at_utc,
        max(executed_at_utc)                as last_traded_at_utc
    from executions
    group by 1

),

asset_classes as (

    select * from {{ ref('instrument_asset_classes') }}

)

select
    instruments.instrument_symbol,
    instruments.instrument_name,
    asset_classes.asset_class,
    instruments.instrument_currency,
    instruments.first_traded_at_utc,
    instruments.last_traded_at_utc
from instruments
left join asset_classes on instruments.instrument_symbol = asset_classes.instrument_symbol
