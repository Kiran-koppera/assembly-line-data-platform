{# Use the folder schema as-is (staging, intermediate, marts) instead of prefixing the target schema. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}

{# Generic test: a numeric column stays within physical limits. #}
{% test within_range(model, column_name, min_value, max_value) %}
select * from {{ model }}
where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}

{# Generic test: combination of columns is unique (small local version of dbt_utils). #}
{% test dbt_utils_unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) from {{ model }}
group by {{ columns | join(', ') }} having count(*) > 1
{% endtest %}
