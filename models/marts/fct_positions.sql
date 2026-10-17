-- Position-level fact: one row per closed position, enriched with instrument
-- attributes. The main table for trade performance analysis.

with positions as (

    select * from {{ ref('int_positions') }}

),

instruments as (

    select instrument_symbol, asset_class
    from {{ ref('dim_instruments') }}

)

select
    positions.position_id,
    positions.instrument_symbol,
    instruments.asset_class,
    positions.side,
    positions.position_size,
    positions.open_price,
    positions.avg_close_price,
    positions.initial_stop_loss,
    positions.initial_take_profit,
    positions.initial_stop_loss is not null         as has_initial_stop_loss,
    positions.initial_take_profit is not null       as has_initial_take_profit,
    positions.stop_loss_timing,
    positions.take_profit_timing,

    positions.opened_at_utc,
    positions.closed_at_utc,
    cast(positions.opened_at_utc as date)           as opened_date,
    cast(positions.closed_at_utc as date)           as closed_date,
    positions.hold_hours,

    positions.exit_reason,
    positions.n_closes,
    positions.is_partially_closed,
    positions.n_modifications,
    positions.n_swaps,

    positions.realized_pnl_usd,
    positions.swap_usd,
    positions.adjustment_usd,
    positions.net_pnl_usd,
    positions.outcome

from positions
left join instruments on positions.instrument_symbol = instruments.instrument_symbol
