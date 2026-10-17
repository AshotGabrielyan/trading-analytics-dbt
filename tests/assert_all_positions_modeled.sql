-- int_positions must contain every position that appears in the executions
-- (an inner join to closes would silently drop a still-open position).

select distinct executions.position_id
from {{ ref('stg_trade_executions') }} as executions
left join {{ ref('fct_positions') }} as positions
    on executions.position_id = positions.position_id
where positions.position_id is null
