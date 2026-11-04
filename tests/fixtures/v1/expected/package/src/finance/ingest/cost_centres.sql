CREATE OR REFRESH MATERIALIZED VIEW ${catalog_finance_silver}.${schema_finance_silver}.cost_centres
AS SELECT
  CAST(`id` AS INT) AS `id`,
  CAST(`label` AS STRING) AS `label`
FROM VALUES
  (NULL, NULL)
AS seed(`id`, `label`)
WHERE false;
