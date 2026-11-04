CREATE OR REFRESH STREAMING TABLE prod_sales.bronze.customers
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/prod_sales/bronze/landing/customers/*.csv', format => 'csv');

CREATE OR REFRESH STREAMING TABLE prod_sales.silver.customers
AS SELECT *
FROM STREAM(prod_sales.bronze.customers);

CREATE OR REFRESH STREAMING TABLE prod_sales.bronze.orders
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/prod_sales/bronze/landing/orders', format => 'json');

CREATE OR REFRESH STREAMING TABLE prod_sales.silver.orders;

CREATE TEMPORARY VIEW conformed_orders (
  CONSTRAINT known_status EXPECT (coalesce(operation = 'DELETE', false) OR coalesce(status IN ('open', 'shipped', 'cancelled'), false)),
  CONSTRAINT has_region EXPECT (coalesce(operation = 'DELETE', false) OR coalesce(region IS NOT NULL, false)) ON VIOLATION FAIL UPDATE
)
AS SELECT *
FROM STREAM(prod_sales.bronze.orders)
WHERE coalesce(operation = 'DELETE', false) OR (coalesce(customer_id IS NOT NULL, false) AND coalesce(amount > 0, false));

CREATE FLOW upsert_orders AS AUTO CDC INTO prod_sales.silver.orders
FROM STREAM(conformed_orders)
KEYS (region, order_id)
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY updated_at
STORED AS SCD TYPE 2;

CREATE OR REFRESH STREAMING TABLE prod_sales.silver.orders_quarantine
AS SELECT
  *,
  concat_ws(', ',
    IF(coalesce(customer_id IS NOT NULL, false), NULL, 'has_customer'),
    IF(coalesce(amount > 0, false), NULL, 'positive_amount')
  ) AS _quarantine_reason
FROM STREAM(prod_sales.bronze.orders)
WHERE NOT (coalesce(operation = 'DELETE', false) OR (coalesce(customer_id IS NOT NULL, false) AND coalesce(amount > 0, false)));

CREATE OR REFRESH STREAMING TABLE prod_sales.bronze.refunds
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/shared/refunds', format => 'parquet');

CREATE OR REFRESH STREAMING TABLE prod_sales.silver.refunds;

CREATE FLOW upsert_refunds AS AUTO CDC INTO prod_sales.silver.refunds
FROM STREAM(prod_sales.bronze.refunds)
KEYS (refund_id)
SEQUENCE BY refunded_at
STORED AS SCD TYPE 1;

CREATE OR REFRESH MATERIALIZED VIEW prod_sales.silver.countries
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

CREATE OR REFRESH MATERIALIZED VIEW prod_finance.silver.cost_centres
AS SELECT
  CAST(`id` AS INT) AS `id`,
  CAST(`label` AS STRING) AS `label`
FROM VALUES
  (NULL, NULL)
AS seed(`id`, `label`)
WHERE false;

CREATE OR REFRESH MATERIALIZED VIEW prod_sales.gold.fct_orders AS
-- Orders with their country's VAT.
SELECT o.order_id, o.amount, c.vat_rate
FROM prod_sales.silver.orders AS o
JOIN prod_sales.silver.countries AS c
  ON o.country = c.code

CREATE OR REFRESH MATERIALIZED VIEW prod_sales.gold.revenue AS
SELECT region, SUM(amount) AS revenue
FROM prod_sales.gold.fct_orders
GROUP BY region

