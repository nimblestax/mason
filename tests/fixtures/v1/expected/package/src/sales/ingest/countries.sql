CREATE OR REFRESH MATERIALIZED VIEW ${catalog_sales_silver}.${schema_sales_silver}.countries
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
