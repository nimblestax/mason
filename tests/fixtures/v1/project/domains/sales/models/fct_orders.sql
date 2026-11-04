-- Orders with their country's VAT.
SELECT o.order_id, o.amount, c.vat_rate
FROM sales.silver.orders AS o
JOIN sales.silver.countries AS c
  ON o.country = c.code
