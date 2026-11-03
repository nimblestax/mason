SELECT region, SUM(amount) AS revenue
FROM sales.gold.fct_orders
GROUP BY region
