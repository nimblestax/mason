CREATE OR REFRESH MATERIALIZED VIEW ${catalog_sales_gold}.${schema_sales_gold}.fct_orders AS
-- Orders with their country's VAT.
SELECT o.order_id, o.amount, c.vat_rate
FROM ${catalog_sales_silver}.${schema_sales_silver}.orders AS o
JOIN ${catalog_sales_silver}.${schema_sales_silver}.countries AS c
  ON o.country = c.code
