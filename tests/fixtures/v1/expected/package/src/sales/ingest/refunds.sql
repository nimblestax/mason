CREATE OR REFRESH STREAMING TABLE ${catalog_sales_bronze}.${schema_sales_bronze}.refunds
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('${path_sales__refunds}', format => 'parquet');

CREATE OR REFRESH STREAMING TABLE ${catalog_sales_silver}.${schema_sales_silver}.refunds;

CREATE FLOW upsert_refunds AS AUTO CDC INTO ${catalog_sales_silver}.${schema_sales_silver}.refunds
FROM STREAM(${catalog_sales_bronze}.${schema_sales_bronze}.refunds)
KEYS (refund_id)
SEQUENCE BY refunded_at
STORED AS SCD TYPE 1;
