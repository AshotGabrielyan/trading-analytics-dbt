-- One row per position (broker "Trade Id"): how it was opened, how and when it
-- was closed, and everything it cost or earned.
-- A position has exactly one OPENED execution and one or more CLOSED executions
-- (partial closes). All positions in the export are fully closed.

with executions as (

    select * from {{ ref('stg_trade_executions') }}

),

opens as (

    select
        position_id,
        instrument_symbol,
        quantity_direction                  as side,
        abs(quantity)                       as position_size,
        price                               as open_price,
        stop_loss                           as initial_stop_loss,
        take_profit                         as initial_take_profit,
        executed_at_utc                     as opened_at_utc
    from executions
    where execution_status = 'OPENED'

),

closes as (

    select
        position_id,
        count(*)                                                    as n_closes,
        sum(abs(quantity) * price) / sum(abs(quantity))             as avg_close_price,
        min(executed_at_utc)                                        as first_closed_at_utc,
        max(executed_at_utc)                                        as closed_at_utc,
        sum(realized_pnl_usd)                                       as realized_pnl_usd,
        -- exit reason = what triggered the final close
        arg_max(execution_source, executed_at_utc)                  as exit_reason
    from executions
    where execution_status = 'CLOSED'
    group by 1

),

financing as (

    -- overnight swaps and broker cash adjustments booked against the position
    select
        position_id,
        count(case when execution_status = 'SWAP' then 1 end)                              as n_swaps,
        coalesce(sum(case when execution_status = 'SWAP' then swap_usd end), 0)           as swap_usd,
        coalesce(sum(case when execution_status = 'CASH_ADJUSTMENT_COMMODITIES' then realized_pnl_usd end), 0)
                                                                                           as adjustment_usd
    from executions
    where execution_status in ('SWAP', 'CASH_ADJUSTMENT_COMMODITIES')
    group by 1

),

modifications as (

    select
        position_id,
        count(*) as n_modifications,
        -- was a level in force after any modification (set or kept)?
        max(case when stop_loss is not null then 1 else 0 end) = 1     as has_modified_stop_loss,
        max(case when take_profit is not null then 1 else 0 end) = 1   as has_modified_take_profit
    from executions
    where execution_status = 'MODIFIED'
    group by 1

),

joined as (

    select
        opens.position_id,
        opens.instrument_symbol,
        opens.side,
        opens.position_size,
        opens.open_price,
        closes.avg_close_price,
        opens.initial_stop_loss,
        opens.initial_take_profit,
        case
            when opens.initial_stop_loss is not null then 'at open'
            when modifications.has_modified_stop_loss then 'added later'
            else 'never'
        end                                                 as stop_loss_timing,
        case
            when opens.initial_take_profit is not null then 'at open'
            when modifications.has_modified_take_profit then 'added later'
            else 'never'
        end                                                 as take_profit_timing,

        opens.opened_at_utc,
        closes.first_closed_at_utc,
        closes.closed_at_utc,
        date_diff('second', opens.opened_at_utc, closes.closed_at_utc) / 3600.0
                                                            as hold_hours,

        closes.exit_reason,
        closes.n_closes,
        closes.n_closes > 1                                 as is_partially_closed,
        coalesce(modifications.n_modifications, 0)          as n_modifications,
        coalesce(financing.n_swaps, 0)                      as n_swaps,

        closes.realized_pnl_usd,
        coalesce(financing.swap_usd, 0)                     as swap_usd,
        coalesce(financing.adjustment_usd, 0)               as adjustment_usd,
        closes.realized_pnl_usd
            + coalesce(financing.swap_usd, 0)
            + coalesce(financing.adjustment_usd, 0)         as net_pnl_usd

    from opens
    inner join closes on opens.position_id = closes.position_id
    left join financing on opens.position_id = financing.position_id
    left join modifications on opens.position_id = modifications.position_id

)

select
    *,
    case
        when net_pnl_usd > 0 then 'win'
        when net_pnl_usd < 0 then 'loss'
        else 'breakeven'
    end as outcome
from joined
