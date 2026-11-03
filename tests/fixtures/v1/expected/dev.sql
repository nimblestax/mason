CREATE OR REFRESH STREAMING TABLE dev_sales.bronze.customers
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/dev_sales/bronze/landing/customers/*.csv', format => 'csv');

CREATE OR REFRESH STREAMING TABLE dev_sales.silver.customers
AS SELECT *
FROM STREAM(dev_sales.bronze.customers);

CREATE OR REFRESH STREAMING TABLE dev_sales.bronze.orders
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/dev_sales/bronze/landing/orders', format => 'json');

CREATE OR REFRESH STREAMING TABLE dev_sales.silver.orders;

CREATE FLOW upsert_orders AS AUTO CDC INTO dev_sales.silver.orders
FROM STREAM(dev_sales.bronze.orders)
KEYS (region, order_id)
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY updated_at
STORED AS SCD TYPE 2;

CREATE OR REFRESH STREAMING TABLE dev_sales.bronze.refunds
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/shared/refunds', format => 'parquet');

CREATE OR REFRESH STREAMING TABLE dev_sales.silver.refunds;

CREATE FLOW upsert_refunds AS AUTO CDC INTO dev_sales.silver.refunds
FROM STREAM(dev_sales.bronze.refunds)
KEYS (refund_id)
SEQUENCE BY refunded_at
STORED AS SCD TYPE 1;

CREATE OR REFRESH MATERIALIZED VIEW dev_sales.silver.countries
AS SELECT
  CAST(`code` AS STRING) AS `code`,
  CAST(`name` AS STRING) AS `name`,
  CAST(`vat_rate` AS DECIMAL(4, 2)) AS `vat_rate`,
  CAST(`joined` AS DATE) AS `joined`,
  CAST(`active` AS BOOLEAN) AS `active`
FROM VALUES
  ('AU', 'Australia', '0.10', '2001-01-01', 'true'),
  ('NZ', 'Aotearoa, New Zealand', '0.15', NULL, 'false'),
  ('GB', 'O\'Brien\'s \u0024{land}', NULL, '2020-02-29', NULL)
AS seed(`code`, `name`, `vat_rate`, `joined`, `active`);

CREATE OR REFRESH MATERIALIZED VIEW dev_finance.silver.cost_centres
AS SELECT
  CAST(`id` AS INT) AS `id`,
  CAST(`label` AS STRING) AS `label`
FROM VALUES
  (NULL, NULL)
AS seed(`id`, `label`)
WHERE false;

CREATE OR REFRESH MATERIALIZED VIEW dev_sales.gold.fct_orders AS
-- Orders with their country's VAT.
SELECT o.order_id, o.amount, c.vat_rate
FROM dev_sales.silver.orders AS o
JOIN dev_sales.silver.countries AS c
  ON o.country = c.code

CREATE OR REFRESH MATERIALIZED VIEW dev_sales.gold.revenue AS
SELECT region, SUM(amount) AS revenue
FROM dev_sales.gold.fct_orders
GROUP BY region

