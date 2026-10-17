{#
    Broker exports timestamps as text like '2026-10-09 11:33:56.303000 +00:00'.
    Parse the offset explicitly and return a naive timestamp in UTC, so date
    truncation never depends on the session time zone.
#}
{% macro parse_broker_timestamp(column_name) -%}
    timezone('UTC', strptime({{ column_name }}, '%Y-%m-%d %H:%M:%S.%f %z'))
{%- endmacro %}
