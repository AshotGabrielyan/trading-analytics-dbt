-- Every position has exactly one OPENED execution and its OPENED + CLOSED
-- quantities net to zero (fully closed). Fails on any position that doesn't.

select
    position_id,
    count(case when execution_status = 'OPENED' then 1 end)                       as n_opened,
    count(case when execution_status = 'CLOSED' then 1 end)                       as n_closed,
    sum(case when execution_status in ('OPENED', 'CLOSED') then quantity end)     as net_quantity
from {{ ref('stg_trade_executions') }}
group by 1
having n_opened <> 1 or n_closed = 0 or net_quantity <> 0
