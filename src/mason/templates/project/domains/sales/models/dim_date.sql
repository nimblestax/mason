SELECT
  date_day,
  year(date_day) AS year,
  quarter(date_day) AS quarter,
  month(date_day) AS month,
  dayofweek(date_day) AS day_of_week
FROM (
  SELECT explode(sequence(DATE'2020-01-01', DATE'2035-12-31', INTERVAL 1 DAY)) AS date_day
)
