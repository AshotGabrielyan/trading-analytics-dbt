{#
    Exports arrive monthly and overlap (each one may repeat earlier rows), and all of
    them stay in data/. Keep every row once, taken from the most recent export.

    The export date comes from the file name ('..._till_16.10.2026.csv'); files without
    a parsable date sort last, then by file name.
    Expects the relation to carry the `filename` column added by read_csv(filename=true).
#}
{% macro latest_export_rows(relation, key_column) -%}
    select * exclude (export_rank)
    from (
        select
            *,
            row_number() over (
                partition by {{ key_column }}
                order by {{ export_date('filename') }} desc nulls last, filename desc
            ) as export_rank
        from {{ relation }}
    ) as ranked
    where export_rank = 1
{%- endmacro %}


{% macro export_date(filename_column) -%}
    try_strptime(regexp_extract({{ filename_column }}, '(\d{2}\.\d{2}\.\d{4})\.csv$', 1), '%d.%m.%Y')
{%- endmacro %}
