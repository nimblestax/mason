CREATE OR REFRESH MATERIALIZED VIEW ${catalog_sales_gold}.${schema_sales_gold}.revenue AS
SELECT region, SUM(amount) AS revenue
FROM ${catalog_sales_gold}.${schema_sales_gold}.fct_orders
GROUP BY region
