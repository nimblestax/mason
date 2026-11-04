---
title: JSON output
description: The envelope every command prints with --json, its exit codes and its rule IDs.
redirects:
  - json-output
---

Every `mason` command accepts `--json`. It prints one envelope on stdout and nothing else there. Logs, including the Databricks CLI's output, go to stderr.

```json
{
  "schema": "mason.validate/1",
  "mason_version": "0.1.0",
  "ok": false,
  "result": {},
  "diagnostics": [
    {
      "rule": "MSN201",
      "name": "unresolved-logical-name",
      "severity": "error",
      "file": "domains/sales/models/fct_orders.sql",
      "line": null,
      "message": "sales.silver.nope isn't a table in this project.",
      "fix": "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
      "docs": "https://github.com/nimblestax/mason-core/blob/main/docs/reference/json-output.md#rule-ids"
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `schema` | The command and the version of its result, such as `mason.validate/1`. A usage error that names no command uses `mason.usage/1`. |
| `mason_version` | The installed Mason. |
| `ok` | Whether the command succeeded. |
| `result` | The command's own output. It is `{}` when the command fails. |
| `diagnostics` | Every problem found. `file` is empty and `line` is `null` when they don't apply. |

`fix` is an instruction in words, not a patch that Mason applies.

## Results

| Command | `result` |
| --- | --- |
| `init` | `project` |
| `validate` | Empty |
| `schema` | `kind`, `version`, `json_schema` |
| `compile` | `package`, or `env` and `sql` with `--env` |
| `deploy` | `env` |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## Rule IDs

Rule IDs are `MSN` plus three digits. An ID never changes meaning, and a retired ID is never reused.

| Rule | Name | Meaning |
| --- | --- | --- |
| `MSN101` | `missing-kind` | A config file has no `kind`. |
| `MSN102` | `unknown-kind` | A `kind` isn't one Mason knows. |
| `MSN103` | `missing-version` | A config file has no `version`. |
| `MSN104` | `unknown-version` | This Mason doesn't support that `version`. |
| `MSN105` | `wrong-kind` | A file's `kind` doesn't belong in its location. |
| `MSN106` | `invalid-field` | A field doesn't match its Kind's schema. |
| `MSN107` | `unreadable-config` | A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file isn't valid CSV. |
| `MSN108` | `sql-without-config` | A SQL file has no config file beside it. |
| `MSN109` | `missing-sql-file` | A model names a SQL file that doesn't exist. |
| `MSN110` | `keys-without-sequence-by` | A Source's `silver` block has `keys` but no `sequence_by`. |
| `MSN111` | `upsert-field-without-keys` | A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`. |
| `MSN112` | `missing-seed-file` | A Seed's `file` doesn't exist beside it. |
| `MSN113` | `seed-header-mismatch` | The first line of a Seed's file doesn't name each declared column once. |
| `MSN114` | `seed-row-mismatch` | A row of a Seed's file has the wrong number of values, or a value that doesn't fit its column's type. |
| `MSN115` | `unsupported-seed-type` | A Seed's column has a type Mason can't check values against. |
| `MSN116` | `invalid-expectation` | An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| `MSN117` | `invalid-name` | A config file's name isn't an identifier, so the table named after it can't be written in SQL: it must hold only letters, digits and underscores, and not start with a digit. |
| `MSN118` | `invalid-delete-when` | A Source's `silver.delete_when` isn't one SQL condition on one row, for the same reasons as `MSN116`. |
| `MSN119` | `invalid-sequence-by` | A Source's `silver.sequence_by` isn't one SQL expression on one row, such as `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| `MSN120` | `duplicate-config-file` | Two config files share a name in one folder, such as `orders.yaml` and `orders.yml`. Mason reads either ending, and writes `.yaml`. |
| `MSN121` | `unlisted-domain-folder` | A folder under `domains/` isn't listed in `domains` in `mason.platform.yaml`, in the same case, so nothing in it is validated or deployed. |
| `MSN201` | `unresolved-logical-name` | SQL reads a table that isn't in the project. |
| `MSN202` | `duplicate-table` | Two tables in one Domain would share a name: a Seed and a Source, or a table and a Source's Quarantine table. |
| `MSN203` | `unparseable-sql` | A Gold Model's SQL doesn't parse as one Databricks SQL query. |
| `MSN204` | `computed-table-name` | SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Mason can't see what it reads. |
| `MSN205` | `real-table-name` | SQL reads a real table name, which names one Environment, instead of its Logical Name. |
| `MSN206` | `file-read` | A Gold Model reads files or external data, such as `read_files(...)` or ``parquet.`/path` ``, instead of a table. |
| `MSN207` | `raw-string-placeholder` | A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`. The pipeline replaces `${name}` with a setting's value, even inside a string. Mason escapes `${` in ordinary strings and comments, but a raw string can't hold the escape. |
| `MSN208` | `model-cycle` | Gold Models read themselves, or each other in a loop, so none of them can run first. |
| `MSN901` | `usage-error` | The command line is wrong. |
| `MSN902` | `unknown-environment` | `--env` isn't an Environment in the project. |
| `MSN903` | `databricks-cli-missing` | `databricks` isn't on the PATH. |
| `MSN904` | `databricks-command-failed` | A Databricks CLI command failed. |
| `MSN905` | `unexpected-error` | Mason stopped on something it didn't expect, with a traceback on stderr. |
| `MSN906` | `pipeline-column-not-found` | The refresh failed because a pipeline names a column its table doesn't have, often an Expectation on a column bronze doesn't have yet. See [Recover from a failed refresh](../guides/recover-from-a-failed-refresh.md). |
| `MSN907` | `expectation-failed` | The refresh failed because a row broke an Expectation whose `action` is `fail`. See [Recover from a failed refresh](../guides/recover-from-a-failed-refresh.md). |
| `MSN908` | `pipeline-failed` | The refresh failed with another pipeline error. The message is the pipeline's own. |

`mason schema <unknown kind>` reports `MSN102` and exits 2, because the mistake is on the command line. Every `MSN1xx` and `MSN2xx` rule exits 1 when found in a project.

When `mason deploy` refreshes an Environment and a pipeline update fails, the diagnostic's `message` is the pipeline's own error, read from its event log: `MSN906`, `MSN907` or `MSN908`, each exiting 2. A pipeline retries a failed update once, so an error a retry can't fix is reported in about a minute. When no pipeline error can be read, Mason reports `MSN904` with the Databricks CLI's last lines.
