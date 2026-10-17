{#
    Standard trade-performance aggregates over fct_positions rows.
    Use inside a SELECT with a GROUP BY (or none, for account totals) so every
    performance mart defines win rate, profit factor, etc. the same way.
#}
{% macro position_performance_metrics() -%}
        count(*)                                                                    as n_positions,
        count(case when outcome = 'win' then 1 end)                                 as n_wins,
        count(case when outcome = 'loss' then 1 end)                                as n_losses,
        round(count(case when outcome = 'win' then 1 end) / count(*), 4)            as win_rate,

        sum(net_pnl_usd)                                                            as net_pnl_usd,
        sum(realized_pnl_usd)                                                       as realized_pnl_usd,
        sum(swap_usd)                                                               as swap_usd,
        coalesce(sum(case when net_pnl_usd > 0 then net_pnl_usd end), 0)            as gross_profit_usd,
        coalesce(-sum(case when net_pnl_usd < 0 then net_pnl_usd end), 0)           as gross_loss_usd,
        round(
            coalesce(sum(case when net_pnl_usd > 0 then net_pnl_usd end), 0)
            / nullif(-sum(case when net_pnl_usd < 0 then net_pnl_usd end), 0),
        4)                                                                          as profit_factor,
        round(avg(case when outcome = 'win' then net_pnl_usd end), 4)               as avg_win_usd,
        round(avg(case when outcome = 'loss' then net_pnl_usd end), 4)              as avg_loss_usd,
        round(avg(net_pnl_usd), 4)                                                  as expectancy_usd,
        max(net_pnl_usd)                                                            as best_position_usd,
        min(net_pnl_usd)                                                            as worst_position_usd,

        round(avg(hold_hours), 2)                                                   as avg_hold_hours,
        round(median(hold_hours), 2)                                                as median_hold_hours,

        count(case when side = 'long' then 1 end)                                   as n_long,
        count(case when side = 'short' then 1 end)                                  as n_short,
        coalesce(sum(case when side = 'long' then net_pnl_usd end), 0)              as long_net_pnl_usd,
        coalesce(sum(case when side = 'short' then net_pnl_usd end), 0)             as short_net_pnl_usd,

        round(count(case when exit_reason = 'TP' then 1 end) / count(*), 4)         as pct_exit_take_profit,
        round(count(case when exit_reason = 'SL' then 1 end) / count(*), 4)         as pct_exit_stop_loss,
        round(count(case when exit_reason = 'USER' then 1 end) / count(*), 4)       as pct_exit_manual,
        round(count(case when exit_reason = 'CLOSE_OUT' then 1 end) / count(*), 4)  as pct_exit_close_out,
        round(count(case when has_initial_stop_loss then 1 end) / count(*), 4)      as pct_opened_with_stop_loss
{%- endmacro %}
