---
title: JSON output
description: The envelope every command prints with --json, its exit codes and its rule IDs.
generated: true
mason_version: 0.1.0
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

## Envelope

The fields of the envelope, in the order they are printed.

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | string | The command and the version of its result, such as `mason.validate/1`. A usage error that names no command uses `mason.usage/1`. |
| `mason_version` | string | The installed Mason. |
| `ok` | boolean | Whether the command succeeded. |
| `result` | object | The command's own output, which its page describes. It is `{}` when the command fails. |
| `diagnostics` | array of object | Every problem found. |

## Diagnostics

Each diagnostic in `diagnostics` is one problem found.

| Field | Type | Meaning |
| --- | --- | --- |
| `rule` | string | The Rule's ID, such as `MSN201`. An ID never changes meaning. |
| `name` | string | The Rule's name, such as `unresolved-logical-name`. |
| `severity` | string | How serious it is. Every diagnostic is an `error`. |
| `file` | string | The file it's in, from the project folder, or empty when none is. |
| `line` | integer or null | The line in `file`, or `null` when it doesn't apply. |
| `message` | string | What is wrong. |
| `fix` | string | What to change, as an instruction in words, not a patch Mason applies. |
| `docs` | string | Where the Rule is explained. |

## Results

Each command's page describes its `result`.

- [`mason init`](commands/init.md): Create a working project.
- [`mason validate`](commands/validate.md): Check config and SQL references, with no workspace.
- [`mason schema`](commands/schema.md): Print a Kind's fields from the installed Mason. Needs no project.
- [`mason compile`](commands/compile.md): Write generated code, or print it for one Environment.
- [`mason deploy`](commands/deploy.md): Deploy to an Environment and refresh its tables.

## Exit codes

Every command exits with one of these.

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## Rule IDs

Rule IDs are `MSN` plus three digits. An ID never changes meaning, and a retired ID is never reused. Each Rule's page says what it checks, why, an example that fails and the fix.

| Rule | Name | Meaning |
| --- | --- | --- |
| [`MSN101`](rules/msn101.md) | `missing-kind` | A config file has no `kind`. |
| [`MSN102`](rules/msn102.md) | `unknown-kind` | A `kind` isn't one Mason knows. |
| [`MSN103`](rules/msn103.md) | `missing-version` | A config file has no `version`. |
| [`MSN104`](rules/msn104.md) | `unknown-version` | This Mason doesn't support that `version`. |
| [`MSN105`](rules/msn105.md) | `wrong-kind` | A file's `kind` doesn't belong in its location. |
| [`MSN106`](rules/msn106.md) | `invalid-field` | A field doesn't match its Kind's schema. |
| [`MSN107`](rules/msn107.md) | `unreadable-config` | A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file isn't valid CSV. |
| [`MSN108`](rules/msn108.md) | `sql-without-config` | A SQL file has no config file beside it. |
| [`MSN109`](rules/msn109.md) | `missing-sql-file` | A model names a SQL file that doesn't exist. |
| [`MSN110`](rules/msn110.md) | `keys-without-sequence-by` | A Source's `silver` block has `keys` but no `sequence_by`. |
| [`MSN111`](rules/msn111.md) | `upsert-field-without-keys` | A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`. |
| [`MSN112`](rules/msn112.md) | `missing-seed-file` | A Seed's `file` doesn't exist beside it. |
| [`MSN113`](rules/msn113.md) | `seed-header-mismatch` | The first line of a Seed's file doesn't name each declared column once. |
| [`MSN114`](rules/msn114.md) | `seed-row-mismatch` | A row of a Seed's file has the wrong number of values, or a value that doesn't fit its column's type. |
| [`MSN115`](rules/msn115.md) | `unsupported-seed-type` | A Seed's column has a type Mason can't check values against. |
| [`MSN116`](rules/msn116.md) | `invalid-expectation` | An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`MSN117`](rules/msn117.md) | `invalid-name` | A config file's name isn't an identifier, so the table named after it can't be written in SQL: it must hold only letters, digits and underscores, and not start with a digit. |
| [`MSN118`](rules/msn118.md) | `invalid-delete-when` | A Source's `silver.delete_when` isn't one SQL condition on one row, for the same reasons as `MSN116`. |
| [`MSN119`](rules/msn119.md) | `invalid-sequence-by` | A Source's `silver.sequence_by` isn't one SQL expression on one row, such as `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`MSN120`](rules/msn120.md) | `duplicate-config-file` | Two config files share a name in one folder, such as `orders.yaml` and `orders.yml`. Mason reads either ending, and writes `.yaml`. |
| [`MSN121`](rules/msn121.md) | `unlisted-domain-folder` | A folder under `domains/` isn't listed in `domains` in `mason.platform.yaml`, in the same case, so nothing in it is validated or deployed. |
| [`MSN201`](rules/msn201.md) | `unresolved-logical-name` | SQL reads a table that isn't in the project. |
| [`MSN202`](rules/msn202.md) | `duplicate-table` | A Seed and a Source in one Domain share a name, so they would be one table. |
| [`MSN203`](rules/msn203.md) | `unparseable-sql` | A Gold Model's SQL doesn't parse as one Databricks SQL query. |
| [`MSN204`](rules/msn204.md) | `computed-table-name` | SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Mason can't see what it reads. |
| [`MSN205`](rules/msn205.md) | `real-table-name` | SQL reads a real table name, which names one Environment, instead of its Logical Name. |
| [`MSN206`](rules/msn206.md) | `file-read` | A Gold Model reads files or external data, such as `read_files(...)` or ``parquet.`/path` ``, instead of a table. |
| [`MSN207`](rules/msn207.md) | `raw-string-placeholder` | A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`. |
| [`MSN208`](rules/msn208.md) | `model-cycle` | Gold Models read themselves, or each other in a loop, so none of them can run first. |
| [`MSN901`](rules/msn901.md) | `usage-error` | The command line is wrong. |
| [`MSN902`](rules/msn902.md) | `unknown-environment` | `--env` isn't an Environment in the project. |
| [`MSN903`](rules/msn903.md) | `databricks-cli-missing` | `databricks` isn't on the PATH. |
| [`MSN904`](rules/msn904.md) | `databricks-command-failed` | A Databricks CLI command failed. |
| [`MSN905`](rules/msn905.md) | `unexpected-error` | Mason stopped on something it didn't expect, with a traceback on stderr. |
| [`MSN906`](rules/msn906.md) | `pipeline-column-not-found` | The refresh failed because a pipeline names a column its table doesn't have, often an Expectation on a column bronze doesn't have yet. |
| [`MSN907`](rules/msn907.md) | `expectation-failed` | The refresh failed because a row broke an Expectation whose `action` is `fail`. |
| [`MSN908`](rules/msn908.md) | `pipeline-failed` | The refresh failed with another pipeline error. The message is the pipeline's own. |

`mason schema <unknown kind>` reports `MSN102` and exits 2, because the mistake is on the command line. Every `MSN1xx` and `MSN2xx` rule exits 1 when found in a project.

When `mason deploy` refreshes an Environment and a pipeline update fails, the diagnostic's `message` is the pipeline's own error, read from its event log: `MSN906`, `MSN907` or `MSN908`, each exiting 2. A pipeline retries a failed update once, so an error a retry can't fix is reported in about a minute. When no pipeline error can be read, Mason reports `MSN904` with the Databricks CLI's last lines.
