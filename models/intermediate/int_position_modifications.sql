-- One row per stop-loss / take-profit change on an open position.
-- Compares each MODIFIED event with the levels in force just before it
-- (from the OPENED row or the previous modification).

with executions as (

    select * from {{ ref('stg_trade_executions') }}

),

positions as (

    select position_id, side, open_price
    from {{ ref('int_positions') }}

),

level_history as (

    select
        exec_id,
        position_id,
        execution_status,
        executed_at_utc,
        stop_loss,
        take_profit,
        lag(stop_loss)   over w as previous_stop_loss,
        lag(take_profit) over w as previous_take_profit,
        row_number()     over w as event_number
    from executions
    where execution_status in ('OPENED', 'MODIFIED')
    window w as (partition by position_id order by executed_at_utc, exec_id)

)

select
    level_history.exec_id,
    level_history.position_id,
    level_history.event_number - 1                      as modification_number,
    level_history.executed_at_utc                       as modified_at_utc,

    level_history.previous_stop_loss,
    level_history.stop_loss,
    level_history.previous_take_profit,
    level_history.take_profit,

    level_history.stop_loss is distinct from level_history.previous_stop_loss
                                                        as is_stop_loss_changed,
    level_history.take_profit is distinct from level_history.previous_take_profit
                                                        as is_take_profit_changed,

    -- tightened = stop moved toward / past the price in the trade's favour
    case
        when level_history.previous_stop_loss is null and level_history.stop_loss is not null then 'added'
        when level_history.previous_stop_loss is not null and level_history.stop_loss is null then 'removed'
        when level_history.stop_loss = level_history.previous_stop_loss then 'unchanged'
        when (positions.side = 'long') = (level_history.stop_loss > level_history.previous_stop_loss) then 'tightened'
        when level_history.stop_loss is not null then 'loosened'
        else 'unchanged'
    end                                                 as stop_loss_change,

    -- stop at or beyond entry price = the trade can no longer lose on the SL
    case positions.side
        when 'long'  then level_history.stop_loss >= positions.open_price
        when 'short' then level_history.stop_loss <= positions.open_price
    end                                                 as is_stop_at_or_past_entry

from level_history
inner join positions on level_history.position_id = positions.position_id
where level_history.execution_status = 'MODIFIED'
