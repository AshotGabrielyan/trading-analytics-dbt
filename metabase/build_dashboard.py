"""Build the 'Trading performance' Metabase dashboard from the dbt marts.

Re-runnable: updates the dashboard in place (same URL) and replaces its cards. On a fresh Metabase
it also creates the admin account and the read-only DuckDB connection.

    docker compose -f metabase/docker-compose.yml up -d --build
    python metabase/build_dashboard.py --email you@example.com
"""
import argparse

from mb import call, ensure_admin, ensure_database

parser = argparse.ArgumentParser()
parser.add_argument('--email', help='admin email, only needed on first run')
parser.add_argument('--first-name', default='Admin')
parser.add_argument('--last-name', default='User')
args = parser.parse_args()
if args.email:
    ensure_admin(args.email, args.first_name, args.last_name)

COLLECTION = 'Trading performance'
GREEN, RED, BLUE, GREY = '#84BB4C', '#ED6E6E', '#509EE3', '#949AAB'

DB = ensure_database()
meta = call('GET', f'/api/database/{DB}/metadata')
FIELD = {(t['name'], f['name']): f['id'] for t in meta['tables'] for f in t['fields']}

# --- collection: reuse it, archive the previous build's cards ----------------------
# The dashboard itself is updated in place so its URL stays the same across rebuilds.
COLL = next((c['id'] for c in call('GET', '/api/collection')
             if c.get('name') == COLLECTION and not c.get('archived') and isinstance(c['id'], int)), None)
if COLL is None:
    COLL = call('POST', '/api/collection', {'name': COLLECTION, 'color': '#509EE3'})['id']
items = call('GET', f'/api/collection/{COLL}/items?models=card&models=dashboard')['data']
EXISTING_DASH = next((i['id'] for i in items if i['model'] == 'dashboard' and i['name'] == 'Trading performance'), None)
OLD_CARDS = [i['id'] for i in items if i['model'] == 'card']

# --- filters ---------------------------------------------------------------------
# Every card declares the template tags it supports; dashboard filters map onto them.
POS_TAGS = {
    'closed': ('fct_positions', 'closed_date', 'date/all-options', 'Closed date'),
    'instrument': ('fct_positions', 'instrument_symbol', 'string/=', 'Instrument'),
    'asset_class': ('fct_positions', 'asset_class', 'string/=', 'Asset class'),
}
BAL_TAGS = {'closed': ('fct_account_balance_daily', 'date_day', 'date/all-options', 'Date')}
LEDGER_TAGS = {'closed': ('fct_ledger_transactions', 'transaction_date', 'date/all-options', 'Date')}

# Positions CTE used by every position-based card. No table alias: Metabase field
# filters render as "marts"."fct_positions"."col" = ?
POSITIONS = """with positions as (
    select * from marts.fct_positions
    where {{closed}} and {{instrument}} and {{asset_class}}
)
"""


def tags(spec):
    return {name: {'id': name, 'name': name, 'display-name': label, 'type': 'dimension',
                   'dimension': ['field', FIELD[(table, col)], None], 'widget-type': widget}
            for name, (table, col, widget, label) in spec.items()}


def usd(*cols, decimals=2):
    return {f'["name","{c}"]': {'number_style': 'currency', 'currency': 'USD',
                                 'currency_style': 'symbol', 'decimals': decimals} for c in cols}


def pct(*cols):
    return {f'["name","{c}"]': {'number_style': 'percent', 'decimals': 1} for c in cols}


def titles(**names):
    return {f'["name","{c}"]': {'column_title': t} for c, t in names.items()}


def merge(*dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            out.setdefault(k, {}).update(v)
    return out


CARDS = {}


def card(key, name, display, sql, tag_spec, viz=None, description=None):
    q = {'database': DB, 'type': 'native', 'native': {'query': sql, 'template-tags': tags(tag_spec)}}
    c = call('POST', '/api/card', {'name': name, 'display': display, 'dataset_query': q,
                                   'visualization_settings': viz or {}, 'collection_id': COLL,
                                   'description': description})
    CARDS[key] = (c['id'], tag_spec)
    return c['id']


# =================================================================================
# Overview
# =================================================================================
def num(decimals):
    return lambda *cols: {f'["name","{c}"]': {'decimals': decimals} for c in cols}


def scalar(key, name, expr, fmt, description=None):
    card(key, name, 'scalar', POSITIONS + f'select {expr} as value from positions', POS_TAGS,
         {'column_settings': fmt('value')}, description)


KPIS = [
    ('kpi_net', 'Net P&L', 'sum(net_pnl_usd)', usd),
    ('kpi_n', 'Positions', 'count(*)', num(0)),
    ('kpi_wr', 'Win rate', "count(case when outcome = 'win' then 1 end) / count(*)", pct),
    ('kpi_pf', 'Profit factor',
     'sum(case when net_pnl_usd > 0 then net_pnl_usd end) / nullif(-sum(case when net_pnl_usd < 0 then net_pnl_usd end), 0)',
     num(2)),
    ('kpi_avg_win', 'Avg win', "avg(case when outcome = 'win' then net_pnl_usd end)", usd),
    ('kpi_avg_loss', 'Avg loss', "avg(case when outcome = 'loss' then net_pnl_usd end)", usd),
    ('kpi_exp', 'Expectancy', 'avg(net_pnl_usd)', usd),
]
for key, name, expr, fmt in KPIS:
    scalar(key, name, expr, fmt)

card('kpi_dd', 'Max drawdown', 'scalar',
     'select min(drawdown_usd) as value from marts.fct_account_balance_daily where {{closed}}',
     BAL_TAGS, {'column_settings': usd('value')},
     'Largest fall of the cumulative trading result from its previous peak (account level).')

card('equity', 'Equity curve', 'line', """select
    date_day,
    cumulative_trading_result_usd as trading_result,
    balance_usd                   as balance,
    cumulative_net_funding_usd    as net_deposits
from marts.fct_account_balance_daily
where {{closed}}
order by date_day""", BAL_TAGS, {
    'graph.dimensions': ['date_day'],
    'graph.metrics': ['trading_result', 'balance', 'net_deposits'],
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'USD',
    'series_settings': {'trading_result': {'color': RED, 'title': 'Cumulative trading result'},
                        'balance': {'color': BLUE, 'title': 'Account balance'},
                        'net_deposits': {'color': GREY, 'title': 'Net deposits', 'line.style': 'dashed'}},
}, 'Cumulative trading result (P&L + swaps + rebates + adjustments) vs. what was deposited.')

card('drawdown', 'Drawdown from peak', 'area', """select date_day, drawdown_usd as drawdown
from marts.fct_account_balance_daily
where {{closed}}
order by date_day""", BAL_TAGS, {
    'graph.dimensions': ['date_day'], 'graph.metrics': ['drawdown'],
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'USD',
    'series_settings': {'drawdown': {'color': RED, 'title': 'Drawdown'}},
})

card('waterfall', 'Where the money went', 'waterfall', """select label, amount
from (
    select
        case
            when transaction_type = 'DEPOSIT'    then 'Deposits'
            when transaction_type = 'WITHDRAWAL' then 'Withdrawals'
            when cash_flow_category = 'trading_pnl' then 'Trading P&L'
            when cash_flow_category = 'financing'   then 'Swaps'
            when cash_flow_category = 'rebate'      then 'Rebates'
            else 'Adjustments'
        end as label,
        case
            when transaction_type = 'DEPOSIT' then 1
            when cash_flow_category = 'trading_pnl' then 2
            when cash_flow_category = 'financing' then 3
            when cash_flow_category = 'rebate' then 4
            when transaction_type = 'WITHDRAWAL' then 6
            else 5
        end as sort_order,
        sum(amount_usd) as amount
    from marts.fct_ledger_transactions
    where {{closed}}
    group by 1, 2
) as t
order by sort_order""", LEDGER_TAGS, {
    'graph.dimensions': ['label'], 'graph.metrics': ['amount'],
    'waterfall.increase_color': GREEN, 'waterfall.decrease_color': RED, 'waterfall.total_color': BLUE,
    'waterfall.show_total': True, 'graph.show_values': True, 'graph.label_value_frequency': 'all',
    'graph.x_axis.axis_enabled': True,
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'USD',
}, 'Every cash movement on the account; the total bar is the ending balance.')

card('monthly', 'Net P&L by month', 'combo', POSITIONS + """select
    date_trunc('month', closed_date) as month,
    case when sum(net_pnl_usd) >= 0 then sum(net_pnl_usd) end as profit,
    case when sum(net_pnl_usd) <  0 then sum(net_pnl_usd) end as loss,
    count(*) as positions
from positions
group by 1
order by 1""", POS_TAGS, {
    'graph.dimensions': ['month'], 'graph.metrics': ['profit', 'loss', 'positions'],
    'stackable.stack_type': 'stacked',
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'Net P&L (USD)',
    'series_settings': {'profit': {'display': 'bar', 'color': GREEN, 'title': 'Profitable month'},
                        'loss': {'display': 'bar', 'color': RED, 'title': 'Losing month'},
                        'positions': {'display': 'line', 'color': GREY, 'axis': 'right', 'title': 'Positions closed'}},
})

# =================================================================================
# Instruments
# =================================================================================
card('instr_pnl', 'Net P&L by instrument', 'row', POSITIONS + """select
    instrument_symbol,
    case when sum(net_pnl_usd) >= 0 then sum(net_pnl_usd) end as profit,
    case when sum(net_pnl_usd) <  0 then sum(net_pnl_usd) end as loss
from positions
group by 1
order by sum(net_pnl_usd)""", POS_TAGS, {
    'graph.dimensions': ['instrument_symbol'], 'graph.metrics': ['profit', 'loss'],
    'stackable.stack_type': 'stacked', 'graph.show_values': True,
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'Net P&L (USD)',
    'series_settings': {'profit': {'color': GREEN, 'title': 'Profit'}, 'loss': {'color': RED, 'title': 'Loss'}},
})

card('instr_scatter', 'Hit rate vs. payoff (instruments with 5+ positions)', 'scatter', POSITIONS + """select
    instrument_symbol,
    count(case when outcome = 'win' then 1 end) / count(*) as win_rate,
    avg(case when outcome = 'win' then net_pnl_usd end)
        / nullif(-avg(case when outcome = 'loss' then net_pnl_usd end), 0) as payoff_ratio,
    count(*) as positions
from positions
group by 1
having count(*) >= 5""", POS_TAGS, {
    'graph.dimensions': ['win_rate'], 'graph.metrics': ['payoff_ratio'], 'scatter.bubble': 'positions',
    'graph.x_axis.title_text': 'Win rate', 'graph.y_axis.title_text': 'Avg win ÷ avg loss',
    'graph.show_values': False,
    'column_settings': pct('win_rate'),
    'series_settings': {'payoff_ratio': {'color': BLUE}},
}, 'Break-even needs win rate × payoff > (1 − win rate). Below payoff 1, you need a win rate above 50% just to stay flat.')

card('instr_table', 'Instrument scorecard', 'table', POSITIONS + """select
    instrument_symbol,
    max(asset_class)                                                         as asset_class,
    count(*)                                                                 as positions,
    count(case when outcome = 'win' then 1 end) / count(*)                   as win_rate,
    avg(case when outcome = 'win' then net_pnl_usd end)                      as avg_win,
    avg(case when outcome = 'loss' then net_pnl_usd end)                     as avg_loss,
    sum(case when net_pnl_usd > 0 then net_pnl_usd end)
        / nullif(-sum(case when net_pnl_usd < 0 then net_pnl_usd end), 0)    as profit_factor,
    min(net_pnl_usd)                                                         as worst_trade,
    count(case when exit_reason = 'CLOSE_OUT' then 1 end)                    as close_outs,
    sum(net_pnl_usd)                                                         as net_pnl
from positions
group by 1
order by net_pnl""", POS_TAGS, {
    'column_settings': merge(usd('avg_win', 'avg_loss', 'worst_trade', 'net_pnl'), pct('win_rate'),
                             {'["name","profit_factor"]': {'decimals': 2}},
                             titles(instrument_symbol='Instrument', asset_class='Asset class',
                                    positions='Positions', win_rate='Win rate', avg_win='Avg win',
                                    avg_loss='Avg loss', profit_factor='Profit factor',
                                    worst_trade='Worst trade', close_outs='Close-outs', net_pnl='Net P&L')),
    'table.column_formatting': [
        {'columns': ['net_pnl'], 'type': 'range', 'colors': [RED, '#FFFFFF', GREEN],
         'min_type': None, 'max_type': None, 'operator': '=', 'value': 0, 'highlight_row': False, 'id': 0},
        {'columns': ['close_outs'], 'type': 'single', 'operator': '>', 'value': 0, 'color': RED,
         'highlight_row': False, 'id': 1},
    ],
})

# =================================================================================
# Behaviour
# =================================================================================
card('exit', 'Result by exit reason', 'combo', POSITIONS + """select
    case exit_reason
        when 'TP' then 'Take profit'
        when 'SL' then 'Stop loss'
        when 'USER' then 'Closed manually'
        when 'CLOSE_OUT' then 'Margin close-out'
        else exit_reason
    end as exit_reason,
    case when sum(net_pnl_usd) >= 0 then sum(net_pnl_usd) end as profit,
    case when sum(net_pnl_usd) <  0 then sum(net_pnl_usd) end as loss,
    count(*) as positions
from positions
group by 1
order by sum(net_pnl_usd)""", POS_TAGS, {
    'graph.dimensions': ['exit_reason'], 'graph.metrics': ['profit', 'loss', 'positions'],
    'stackable.stack_type': 'stacked', 'graph.show_values': True,
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'Net P&L (USD)',
    'series_settings': {'profit': {'display': 'bar', 'color': GREEN, 'title': 'Net profit'},
                        'loss': {'display': 'bar', 'color': RED, 'title': 'Net loss'},
                        'positions': {'display': 'line', 'color': GREY, 'axis': 'right', 'title': 'Positions'}},
}, 'What closed each position: your take-profit, your stop-loss, you, or the broker (margin close-out).')

card('hold', 'Result by holding time', 'combo', POSITIONS + """select
    case
        when hold_hours < 5.0 / 60  then '< 5 min'
        when hold_hours < 15.0 / 60 then '5–15 min'
        when hold_hours < 1         then '15–60 min'
        when hold_hours < 4         then '1–4 h'
        when hold_hours < 24        then '4–24 h'
        else '> 1 day'
    end as holding_time,
    case when sum(net_pnl_usd) >= 0 then sum(net_pnl_usd) end as profit,
    case when sum(net_pnl_usd) <  0 then sum(net_pnl_usd) end as loss,
    count(case when outcome = 'win' then 1 end) / count(*) as win_rate
from positions
group by 1
order by min(hold_hours)""", POS_TAGS, {
    'graph.dimensions': ['holding_time'], 'graph.metrics': ['profit', 'loss', 'win_rate'],
    'stackable.stack_type': 'stacked',
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'Net P&L (USD)',
    'column_settings': pct('win_rate'),
    'series_settings': {'profit': {'display': 'bar', 'color': GREEN, 'title': 'Net profit'},
                        'loss': {'display': 'bar', 'color': RED, 'title': 'Net loss'},
                        'win_rate': {'display': 'line', 'color': GREY, 'axis': 'right', 'title': 'Win rate'}},
})

card('distribution', 'P&L per trade: distribution', 'bar', POSITIONS + """select
    case
        when net_pnl_usd < -20 then '< −20'
        when net_pnl_usd < -10 then '−20 to −10'
        when net_pnl_usd < -5  then '−10 to −5'
        when net_pnl_usd < -2  then '−5 to −2'
        when net_pnl_usd < 0   then '−2 to 0'
        when net_pnl_usd < 2   then '0 to 2'
        when net_pnl_usd < 5   then '2 to 5'
        when net_pnl_usd < 10  then '5 to 10'
        else '≥ 10'
    end as pnl_bucket,
    count(case when net_pnl_usd < 0 then 1 end)  as losing_trades,
    count(case when net_pnl_usd >= 0 then 1 end) as winning_trades
from positions
group by 1
order by min(net_pnl_usd)""", POS_TAGS, {
    'graph.dimensions': ['pnl_bucket'], 'graph.metrics': ['losing_trades', 'winning_trades'],
    'stackable.stack_type': 'stacked', 'graph.show_values': True,
    'graph.x_axis.title_text': 'Net P&L per position (USD)', 'graph.y_axis.title_text': 'Positions',
    'series_settings': {'losing_trades': {'color': RED, 'title': 'Losing'},
                        'winning_trades': {'color': GREEN, 'title': 'Winning / flat'}},
}, 'Many small wins, a few large losses: the left tail is what drives the result.')

card('hour', 'Result by hour opened (UTC)', 'combo', POSITIONS + """select
    hour(opened_at_utc) as hour_utc,
    case when sum(net_pnl_usd) >= 0 then sum(net_pnl_usd) end as profit,
    case when sum(net_pnl_usd) <  0 then sum(net_pnl_usd) end as loss,
    count(*) as positions
from positions
group by 1
order by 1""", POS_TAGS, {
    'graph.dimensions': ['hour_utc'], 'graph.metrics': ['profit', 'loss', 'positions'],
    'stackable.stack_type': 'stacked', 'graph.x_axis.scale': 'ordinal',
    'graph.x_axis.title_text': 'Hour of day (UTC)', 'graph.y_axis.title_text': 'Net P&L (USD)',
    'series_settings': {'profit': {'display': 'bar', 'color': GREEN, 'title': 'Net profit'},
                        'loss': {'display': 'bar', 'color': RED, 'title': 'Net loss'},
                        'positions': {'display': 'line', 'color': GREY, 'axis': 'right', 'title': 'Positions'}},
})

card('weekday', 'Result by weekday opened', 'combo', POSITIONS + """select
    strftime(opened_at_utc, '%a') as weekday,
    case when sum(net_pnl_usd) >= 0 then sum(net_pnl_usd) end as profit,
    case when sum(net_pnl_usd) <  0 then sum(net_pnl_usd) end as loss,
    count(*) as positions
from positions
group by 1
order by min(isodow(opened_at_utc))""", POS_TAGS, {
    'graph.dimensions': ['weekday'], 'graph.metrics': ['profit', 'loss', 'positions'],
    'stackable.stack_type': 'stacked',
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'Net P&L (USD)',
    'series_settings': {'profit': {'display': 'bar', 'color': GREEN, 'title': 'Net profit'},
                        'loss': {'display': 'bar', 'color': RED, 'title': 'Net loss'},
                        'positions': {'display': 'line', 'color': GREY, 'axis': 'right', 'title': 'Positions'}},
})

card('side', 'Long vs. short', 'table', POSITIONS + """select
    side,
    count(*)                                               as positions,
    count(case when outcome = 'win' then 1 end) / count(*) as win_rate,
    avg(case when outcome = 'win' then net_pnl_usd end)    as avg_win,
    avg(case when outcome = 'loss' then net_pnl_usd end)   as avg_loss,
    sum(net_pnl_usd)                                       as net_pnl
from positions
group by 1
order by 1""", POS_TAGS, {
    'column_settings': merge(usd('avg_win', 'avg_loss', 'net_pnl'), pct('win_rate'),
                             titles(side='Side', positions='Positions', win_rate='Win rate',
                                    avg_win='Avg win', avg_loss='Avg loss', net_pnl='Net P&L')),
})

card('worst', '10 worst positions', 'table', POSITIONS + """select
    closed_date, instrument_symbol, side, exit_reason, has_initial_stop_loss,
    round(hold_hours, 2) as hold_hours, net_pnl_usd
from positions
order by net_pnl_usd
limit 10""", POS_TAGS, {
    'column_settings': merge(usd('net_pnl_usd'),
                             titles(closed_date='Closed', instrument_symbol='Instrument', side='Side',
                                    exit_reason='Exit', has_initial_stop_loss='Had SL',
                                    hold_hours='Hold (h)', net_pnl_usd='Net P&L')),
})

# =================================================================================
# Stop-loss & take-profit
# =================================================================================
scalar('risk_sl_open', 'Opened with a stop-loss',
       "count(case when stop_loss_timing = 'at open' then 1 end) / count(*)", pct)
scalar('risk_sl_never', 'Never had a stop-loss',
       "count(case when stop_loss_timing = 'never' then 1 end) / count(*)", pct,
       'Share of positions with no stop-loss at any point: not at open and not added later.')
scalar('risk_pnl_never', 'Net P&L, never had a stop-loss',
       "sum(case when stop_loss_timing = 'never' then net_pnl_usd end)", usd)
scalar('risk_pnl_with', 'Net P&L, had a stop-loss',
       "sum(case when stop_loss_timing <> 'never' then net_pnl_usd end)", usd,
       'Stop-loss set at open or added later.')

TIMING_COLUMNS = """
    count(*)                                                    as positions,
    count(*) / sum(count(*)) over ()                            as share,
    count(case when outcome = 'win' then 1 end) / count(*)      as win_rate,
    avg(case when outcome = 'win' then net_pnl_usd end)         as avg_win,
    avg(case when outcome = 'loss' then net_pnl_usd end)        as avg_loss,
    min(net_pnl_usd)                                            as worst_trade,
    count(case when exit_reason = 'CLOSE_OUT' then 1 end)       as close_outs,
    sum(case when net_pnl_usd < 0 then net_pnl_usd end)         as total_lost,
    sum(net_pnl_usd)                                            as net_pnl"""
TIMING_VIZ = {
    'column_settings': merge(usd('avg_win', 'avg_loss', 'worst_trade', 'total_lost', 'net_pnl'),
                             pct('share', 'win_rate'),
                             titles(positions='Positions', share='Share', win_rate='Win rate',
                                    avg_win='Avg win', avg_loss='Avg loss', worst_trade='Worst trade',
                                    close_outs='Close-outs', total_lost='Total lost', net_pnl='Net P&L')),
    'table.column_formatting': [
        {'columns': ['net_pnl'], 'type': 'range', 'colors': [RED, '#FFFFFF', GREEN],
         'min_type': None, 'max_type': None, 'operator': '=', 'value': 0, 'highlight_row': False, 'id': 0},
        {'columns': ['close_outs'], 'type': 'single', 'operator': '>', 'value': 0, 'color': RED,
         'highlight_row': False, 'id': 1},
    ],
}


def timing_viz(**first_column_title):
    return dict(TIMING_VIZ, column_settings={**TIMING_VIZ['column_settings'], **titles(**first_column_title)})


TIMING_ORDER = "case {col} when 'at open' then 1 when 'added later' then 2 else 3 end"

for key, col, label in (('sl_timing', 'stop_loss_timing', 'Stop-loss'),
                        ('tp_timing', 'take_profit_timing', 'Take-profit')):
    card(key, f'{label}: set at open, added later, or never', 'table', POSITIONS + f"""select
    {col} as {col},{TIMING_COLUMNS}
from positions
group by 1
order by {TIMING_ORDER.format(col=col)}""", POS_TAGS, timing_viz(**{col: label}),
        f"'At open' = on the opening order; 'added later' = set by a modification while the position was open.")

card('protection', 'Protection at open: stop-loss and take-profit', 'table', POSITIONS + f"""select
    case
        when has_initial_stop_loss and has_initial_take_profit then 'SL + TP'
        when has_initial_stop_loss then 'SL only'
        when has_initial_take_profit then 'TP only'
        else 'Neither'
    end as opened_with,{TIMING_COLUMNS}
from positions
group by 1
order by min(case
    when has_initial_stop_loss and has_initial_take_profit then 1
    when has_initial_stop_loss then 2
    when has_initial_take_profit then 3
    else 4 end)""", POS_TAGS, timing_viz(opened_with='Opened with'))

card('exit_by_sl', 'How each exit was protected (stop-loss timing)', 'bar', POSITIONS + """select
    case exit_reason
        when 'TP' then 'Take profit'
        when 'SL' then 'Stop loss'
        when 'USER' then 'Closed manually'
        when 'CLOSE_OUT' then 'Margin close-out'
        else exit_reason
    end as exit_reason,
    count(case when stop_loss_timing = 'at open' then 1 end)     as sl_at_open,
    count(case when stop_loss_timing = 'added later' then 1 end) as sl_added_later,
    count(case when stop_loss_timing = 'never' then 1 end)       as sl_never
from positions
group by 1
order by count(*) desc""", POS_TAGS, {
    'graph.dimensions': ['exit_reason'], 'graph.metrics': ['sl_at_open', 'sl_added_later', 'sl_never'],
    'stackable.stack_type': 'stacked', 'graph.show_values': True,
    'graph.x_axis.title_text': ' ', 'graph.y_axis.title_text': 'Positions',
    'series_settings': {'sl_at_open': {'color': GREEN, 'title': 'SL at open'},
                        'sl_added_later': {'color': '#F9CF48', 'title': 'SL added later'},
                        'sl_never': {'color': RED, 'title': 'Never had SL'}},
}, 'E.g. of the positions closed by a stop-loss, how many had it from the start vs. added it later.')

card('loss_by_sl', 'Losses by stop-loss timing', 'combo', POSITIONS + f"""select
    stop_loss_timing,
    sum(case when net_pnl_usd < 0 then net_pnl_usd end)  as total_lost,
    avg(case when outcome = 'loss' then net_pnl_usd end) as avg_loss
from positions
group by 1
order by {TIMING_ORDER.format(col='stop_loss_timing')}""", POS_TAGS, {
    'graph.dimensions': ['stop_loss_timing'], 'graph.metrics': ['total_lost', 'avg_loss'],
    'graph.show_values': True,
    'graph.x_axis.title_text': 'Stop-loss', 'graph.y_axis.title_text': 'Total lost (USD)',
    'column_settings': usd('total_lost', 'avg_loss'),
    'series_settings': {'total_lost': {'display': 'bar', 'color': RED, 'title': 'Total lost'},
                        'avg_loss': {'display': 'line', 'color': GREY, 'axis': 'right', 'title': 'Avg loss'}},
}, 'Sum and average of losing positions only.')

# =================================================================================
# Trade log
# =================================================================================
card('log', 'All positions', 'table', POSITIONS + """select
    closed_at_utc, instrument_symbol, asset_class, side, position_size,
    open_price, avg_close_price, initial_stop_loss, initial_take_profit,
    stop_loss_timing, take_profit_timing,
    round(hold_hours * 60, 1) as hold_minutes, exit_reason, n_modifications,
    realized_pnl_usd, swap_usd, net_pnl_usd, outcome
from positions
order by closed_at_utc desc""", POS_TAGS, {
    'column_settings': merge(usd('realized_pnl_usd', 'swap_usd', 'net_pnl_usd'),
                             titles(closed_at_utc='Closed (UTC)', instrument_symbol='Instrument',
                                    asset_class='Asset class', side='Side', position_size='Size',
                                    open_price='Open', avg_close_price='Close', initial_stop_loss='Initial SL',
                                    initial_take_profit='Initial TP',
                                    stop_loss_timing='SL set', take_profit_timing='TP set', hold_minutes='Hold (min)',
                                    exit_reason='Exit', n_modifications='SL/TP edits',
                                    realized_pnl_usd='Realized', swap_usd='Swaps', net_pnl_usd='Net P&L',
                                    outcome='Outcome')),
    'table.column_formatting': [
        {'columns': ['net_pnl_usd'], 'type': 'range', 'colors': [RED, '#FFFFFF', GREEN],
         'min_type': None, 'max_type': None, 'operator': '=', 'value': 0, 'highlight_row': False, 'id': 0},
    ],
})

# =================================================================================
# Dashboard
# =================================================================================
PARAMS = [
    {'id': 'closed', 'name': 'Date', 'slug': 'date', 'type': 'date/all-options', 'sectionId': 'date'},
    {'id': 'instrument', 'name': 'Instrument', 'slug': 'instrument', 'type': 'string/=', 'sectionId': 'string'},
    {'id': 'asset_class', 'name': 'Asset class', 'slug': 'asset_class', 'type': 'string/=', 'sectionId': 'string'},
]
DASH_FIELDS = {
    'name': 'Trading performance', 'collection_id': COLL, 'parameters': PARAMS,
    'description': 'Built on the dbt marts (marts.*). Date filters closed date for positions and the '
                   'calendar day for balance and ledger cards. Instrument and asset class filters apply '
                   'to position-based cards only.'}
if EXISTING_DASH:
    dash = call('PUT', f'/api/dashboard/{EXISTING_DASH}', DASH_FIELDS)
else:
    dash = call('POST', '/api/dashboard', DASH_FIELDS)

# Headline finding for the Overview subtitle, computed at build time over all positions
# (the text doesn't follow the dashboard filters, so it says "all positions").
win_rate, avg_win, avg_loss, net_pnl = call('POST', '/api/dataset', {'database': DB, 'type': 'native', 'native': {
    'query': """select
        count(case when outcome = 'win' then 1 end) / count(*),
        avg(case when outcome = 'win' then net_pnl_usd end),
        avg(case when outcome = 'loss' then net_pnl_usd end),
        sum(net_pnl_usd)
    from marts.fct_positions"""}})['data']['rows'][0]
HEADLINE = (f'{win_rate:.0%} of trades won, but the average loss was {-avg_loss / avg_win:.1f}× the average win, '
            f"so the account {'lost' if net_pnl < 0 else 'made'} money overall "
            f'({net_pnl:+,.2f} USD across all positions).')

TABS = ['Overview', 'Instruments', 'Behaviour', 'Stop-loss & take-profit', 'Trade log']
LAYOUT = {  # tab -> [(card key | text, col, row, width, height)]
    'Overview': [
        (f'# How did the account do?\n{HEADLINE}\n\n'
         '<sub>Position cards follow the filters; equity, drawdown and the waterfall are account level.</sub>',
         0, 0, 24, 2),
        # row 1: account summary · row 2: why ("wins often, wins small, loses big")
        ('kpi_net', 0, 2, 6, 3), ('kpi_n', 6, 2, 6, 3), ('kpi_exp', 12, 2, 6, 3), ('kpi_dd', 18, 2, 6, 3),
        ('kpi_wr', 0, 5, 6, 3), ('kpi_avg_win', 6, 5, 6, 3), ('kpi_avg_loss', 12, 5, 6, 3),
        ('kpi_pf', 18, 5, 6, 3),
        # equity and drawdown share the full width so their date axes line up
        ('equity', 0, 8, 24, 7),
        ('drawdown', 0, 15, 24, 4),
        ('waterfall', 0, 19, 24, 6),
        ('monthly', 0, 25, 24, 7),
    ],
    'Instruments': [
        ('# Where was money made and lost?', 0, 0, 24, 1),
        ('instr_pnl', 0, 1, 12, 9), ('instr_scatter', 12, 1, 12, 9),
        ('instr_table', 0, 10, 24, 9),
    ],
    'Behaviour': [
        ('# Which habits drive the result?', 0, 0, 24, 1),
        ('exit', 0, 1, 12, 7), ('side', 12, 1, 12, 7),
        ('distribution', 0, 8, 12, 7), ('hold', 12, 8, 12, 7),
        ('hour', 0, 15, 12, 7), ('weekday', 12, 15, 12, 7),
        ('worst', 0, 22, 24, 6),
    ],
    'Stop-loss & take-profit': [
        ('# Do stop-losses and take-profits pay off?\n"Never" means no level at any point while the '
         'position was open; "added later" means set by a modification after opening.', 0, 0, 24, 2),
        ('risk_sl_open', 0, 2, 6, 3), ('risk_sl_never', 6, 2, 6, 3),
        ('risk_pnl_never', 12, 2, 6, 3), ('risk_pnl_with', 18, 2, 6, 3),
        ('sl_timing', 0, 5, 24, 4),
        ('tp_timing', 0, 9, 24, 4),
        ('protection', 0, 13, 24, 5),
        ('exit_by_sl', 0, 18, 12, 7), ('loss_by_sl', 12, 18, 12, 7),
    ],
    'Trade log': [('log', 0, 0, 24, 16)],
}

tabs = [{'id': -(i + 1), 'name': name} for i, name in enumerate(TABS)]
dashcards, next_id = [], -1
for i, tab in enumerate(TABS):
    for key, col, row, w, h in LAYOUT[tab]:
        dc = {'id': next_id, 'dashboard_tab_id': -(i + 1), 'col': col, 'row': row, 'size_x': w, 'size_y': h}
        next_id -= 1
        if key in CARDS:
            card_id, tag_spec = CARDS[key]
            dc.update(card_id=card_id, visualization_settings={}, parameter_mappings=[
                {'parameter_id': p, 'card_id': card_id, 'target': ['dimension', ['template-tag', p]]}
                for p in tag_spec])
        else:  # markdown text card
            dc.update(card_id=None, parameter_mappings=[], visualization_settings={
                'virtual_card': {'name': None, 'display': 'text', 'visualization_settings': {},
                                 'dataset_query': {}, 'archived': False},
                'text': key, 'dashcard.background': False})
        dashcards.append(dc)

call('PUT', f"/api/dashboard/{dash['id']}", {'tabs': tabs, 'dashcards': dashcards})
for card_id in OLD_CARDS:  # previous build's cards, no longer on the dashboard
    call('PUT', f'/api/card/{card_id}', {'archived': True})
print(f"dashboard: http://localhost:3000/dashboard/{dash['id']}")

# smoke test: run every card unfiltered
bad = []
for key, (cid, _) in CARDS.items():
    r = call('POST', f'/api/card/{cid}/query', {'parameters': []})
    if r.get('error') or r.get('status') == 'failed':
        bad.append((key, r.get('error')))
    else:
        print(f"  ok  {key:14} rows={r['row_count']}")
print('FAILED:', bad if bad else 'none')
