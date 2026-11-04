CREATE OR REFRESH STREAMING TABLE ${catalog_sales_bronze}.${schema_sales_bronze}.orders
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('${path_sales__orders}', format => 'json');

CREATE OR REFRESH STREAMING TABLE ${catalog_sales_silver}.${schema_sales_silver}.orders;

CREATE TEMPORARY VIEW conformed_orders (
  CONSTRAINT known_status EXPECT (coalesce(operation = 'DELETE', false) OR coalesce(status IN ('open', 'shipped', 'cancelled'), false)),
  CONSTRAINT has_region EXPECT (coalesce(operation = 'DELETE', false) OR coalesce(region IS NOT NULL, false)) ON VIOLATION FAIL UPDATE
)
AS SELECT *
FROM STREAM(${catalog_sales_bronze}.${schema_sales_bronze}.orders)
WHERE coalesce(operation = 'DELETE', false) OR (coalesce(customer_id IS NOT NULL, false) AND coalesce(amount > 0, false));

CREATE FLOW upsert_orders AS AUTO CDC INTO ${catalog_sales_silver}.${schema_sales_silver}.orders
FROM STREAM(conformed_orders)
KEYS (region, order_id)
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY updated_at
STORED AS SCD TYPE 2;

CREATE OR REFRESH STREAMING TABLE ${catalog_sales_silver}.${schema_sales_silver}.orders_quarantine
AS SELECT
  *,
  concat_ws(', ',
    IF(coalesce(customer_id IS NOT NULL, false), NULL, 'has_customer'),
    IF(coalesce(amount > 0, false), NULL, 'positive_amount')
  ) AS _quarantine_reason
FROM STREAM(${catalog_sales_bronze}.${schema_sales_bronze}.orders)
WHERE NOT (coalesce(operation = 'DELETE', false) OR (coalesce(customer_id IS NOT NULL, false) AND coalesce(amount > 0, false)));
