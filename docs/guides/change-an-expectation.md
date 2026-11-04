---
title: Change an Expectation
description: What adding, changing or removing a quarantining Expectation does to rows already in silver, and how to fully refresh silver so every row meets the new rule.
---

An Expectation's `action` decides whether changing it moves rows. A `warn` or `fail` rule moves no rows, so you can add, change or remove one and deploy as usual. A `quarantine` rule, which is also what a rule with no `action` does, decides which rows reach silver. Adding, changing or removing one needs a full refresh of that Source's silver table.

## What a changed quarantining rule does

Silver is a streaming table. Each row is checked once, when it arrives from bronze, so a new or changed rule reaches only rows that arrive after you deploy it. Rows already in silver aren't checked again.

Say an append Source has been landing orders for a month, and you add a rule:

```yaml
silver:
  expectations:
    - name: positive_amount
      expect: amount > 0
      action: quarantine
```

After `mason deploy`:

- New orders with `amount <= 0` go to the Quarantine table, `<source>_quarantine` in silver's schema, and stay out of silver. This is what the rule asks for.
- Older orders with `amount <= 0` stay in silver, because they arrived before the rule.
- Those older orders are also in the Quarantine table, because a new Quarantine table reads bronze from the start.

So until you refresh, silver holds rows that fail its own rule, and some rows are in silver and in Quarantine at once. Changing or removing a quarantining rule also goes wrong the other way: rows the old rule kept out stay out of silver, even when they meet the rules you have now. The streaming tables keep running, for append and upsert Sources alike. Only the old rows are wrong.

## Fully refresh silver

A full refresh empties the silver table and replays every row of bronze through the current rules. Bronze is never reset, so nothing is lost. Do it in each Environment after the change is deployed there.

1. Deploy the change as usual, for example `mason deploy --env dev`. This writes the Build Package to `build/` and deploys it.
2. Find the real names of the Source's silver and Quarantine tables in this Environment. `mason compile --env dev` prints them, such as `dev_sales.silver.orders` and `dev_sales.silver.orders_quarantine`.
3. From `build/`, fully refresh both tables in the Domain's ingest pipeline. Its key in `databricks.yml` is `<domain>_ingest`:

   ```sh
   cd build
   databricks bundle run sales_ingest --target dev \
     --full-refresh dev_sales.silver.orders,dev_sales.silver.orders_quarantine
   ```

   If you removed the Source's last quarantining rule, it has no Quarantine table any more, so refresh silver alone.

4. Refresh gold so it reads the new silver: `databricks bundle run refresh --target dev`, or the next `mason deploy`.

You can do step 3 in the workspace instead: open the pipeline named `<name>_<domain>_ingest`, where `<name>` is the `name` in `mason.platform.yaml`, select the two tables in its graph, and choose **Full refresh selection**.

A full refresh reads all of bronze, so on a large Source it costs compute and time. Run it when the pipeline isn't busy.

## A rule that doesn't need a refresh

A `warn` rule keeps every row and counts the ones that fail it. A `fail` rule stops the update when a row fails it. Neither moves rows between silver and Quarantine, so adding, changing or removing one is safe with no refresh.
