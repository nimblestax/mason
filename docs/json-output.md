# JSON output

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
      "fix": "Declare a Source or Gold Model with this name, or correct the Logical Name.",
      "docs": "https://github.com/nimblestax/mason-core/blob/main/docs/json-output.md#rule-ids"
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
| `MSN107` | `unreadable-config` | A config file is missing, isn't valid YAML or isn't a mapping. |
| `MSN108` | `sql-without-config` | A SQL file has no config file beside it. |
| `MSN109` | `missing-sql-file` | A model names a SQL file that doesn't exist. |
| `MSN110` | `keys-without-sequence-by` | A Source's `silver` block has `keys` but no `sequence_by`. |
| `MSN111` | `upsert-field-without-keys` | A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`. |
| `MSN112` | `path-missing-for-environment` | A Source's per-Environment `path` has no value for an Environment in the Platform Contract. |
| `MSN201` | `unresolved-logical-name` | SQL reads a table that isn't in the project. |
| `MSN901` | `usage-error` | The command line is wrong. |
| `MSN902` | `unknown-environment` | `--env` isn't an Environment in the project. |
| `MSN903` | `databricks-cli-missing` | `databricks` isn't on the PATH. |
| `MSN904` | `databricks-command-failed` | A Databricks CLI command failed. |
| `MSN905` | `unexpected-error` | Mason stopped on something it didn't expect, with a traceback on stderr. |

`mason schema <unknown kind>` reports `MSN102` and exits 2, because the mistake is on the command line. `MSN101` to `MSN112` and `MSN201` exit 1 when found in a project.
