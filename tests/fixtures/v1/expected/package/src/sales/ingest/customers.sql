CREATE OR REFRESH STREAMING TABLE ${catalog_sales_bronze}.${schema_sales_bronze}.customers
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('${path_sales__customers}', format => 'csv');

CREATE OR REFRESH STREAMING TABLE ${catalog_sales_silver}.${schema_sales_silver}.customers
AS SELECT *
FROM STREAM(${catalog_sales_bronze}.${schema_sales_bronze}.customers);
