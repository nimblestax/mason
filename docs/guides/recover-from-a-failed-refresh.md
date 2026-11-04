---
title: Recover from a failed refresh
description: What to do when mason deploy reports MSN906 or MSN907, and why landing new data doesn't help.
---

`mason deploy` ships an Environment and then refreshes its tables. If a pipeline update fails, Mason reads the pipeline's own error and reports it. A pipeline retries a failed update once, so a one-off blip passes, and an error a retry can't fix is reported in about a minute.

Two failures need a change to the project before the next deploy can pass.

## An Expectation names a column bronze doesn't have yet

`MSN906` (`pipeline-column-not-found`), with a message such as:

```text
[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column, variable, or function parameter with name `region` cannot be resolved.
```

You added a column to a Source's files and an Expectation that checks it in the same change. The silver flow fails analysis on the unknown column before bronze runs, so bronze never picks the column up, and landing new data doesn't help.

1. Remove the Expectation and deploy. Bronze picks up the new column.
2. Add the Expectation back and deploy again.

If no Expectation names the column, the column's name is wrong: correct it in the Expectation or the Model's SQL.

## A `fail` Expectation fired

`MSN907` (`expectation-failed`), with a message such as:

```text
[EXPECTATION_VIOLATION.VERBOSITY_ALL] Flow 'orders' failed to meet the expectation. Violated expectations: 'amount_not_negative'
```

A row broke an Expectation whose `action` is `fail`. Bronze is append-only, so the row stays there, and every refresh fails on the same row until the rule changes. Landing a corrected row doesn't remove the bad one.

Choose one, then deploy again:

- **Correct the rule**, if the row is fine and the rule was wrong.
- **Change its `action` to `quarantine`**, to keep the row out of silver and in the Source's Quarantine table, with the rule's name as the reason.
- **Change its `action` to `warn`**, to keep the row in silver and count it.

```yaml
silver:
  expectations:
    - name: amount_not_negative
      expect: amount >= 0
      action: quarantine
```

## Any other failure

`MSN908` (`pipeline-failed`) carries the pipeline's error as its message. Fix the cause and deploy again; the pipeline's event log in the workspace has the full detail. If Mason couldn't read any pipeline error, it reports `MSN904` with the Databricks CLI's last lines, and the full output is on stderr.
