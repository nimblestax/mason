CREATE OR REFRESH STREAMING TABLE ${catalog_sales_bronze}.${schema_sales_bronze}.orders
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('${path_sales__orders}', format => 'json');

CREATE OR REFRESH STREAMING TABLE ${catalog_sales_silver}.${schema_sales_silver}.orders;

CREATE FLOW upsert_orders AS AUTO CDC INTO ${catalog_sales_silver}.${schema_sales_silver}.orders
FROM STREAM(${catalog_sales_bronze}.${schema_sales_bronze}.orders)
KEYS (region, order_id)
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY updated_at
STORED AS SCD TYPE 2;
