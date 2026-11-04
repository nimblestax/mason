---
title: Source
description: An external dataset landed in bronze and conformed into silver.
generated: true
mason_version: 0.1.0
---

A file with `kind: source`, at version 1. `mason schema source` prints the same fields from the Mason you installed.

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `kind` | `source` | yes |  | The Kind of this file. |
| `version` | `1` | yes |  | The schema version of this Kind. |
| `path` | string | yes |  | Where the files land, such as a Unity Catalog Volume path. `{env}` becomes the Environment's name. |
| `format` | one of `avro`, `binaryFile`, `csv`, `json`, `orc`, `parquet`, `text`, `xml` | yes |  | The format of the files at `path`. |
| `silver` | object | no | `{}` | How silver is written, with `keys`, `sequence_by`, `scd` and `delete_when`. With no keys, it is append-only. `expectations` lists the rules each row must meet, which a delete skips. |
| `silver.keys` | list of string | no | `null` | The columns that identify a row, which turn on upserts. |
| `silver.sequence_by` | string | no | `null` | The column or expression that orders changes to a key. |
| `silver.scd` | one of `1`, `2` | no | `1` | 1 keeps the latest row per key, 2 keeps every version. |
| `silver.delete_when` | string | no | `null` | A SQL condition that marks a change as a delete. |
| `silver.expectations` | list of object | no | `[]` | Row-level rules each row of silver is checked against, in every Environment. On an upsert, a row where `delete_when` is true skips them. |
| `silver.expectations[].name` | string | yes |  | The rule's name, in snake_case. It is the reason a row is quarantined. |
| `silver.expectations[].expect` | string | yes |  | A SQL condition on one row that a good row meets. |
| `silver.expectations[].action` | one of `warn`, `quarantine`, `fail` | no | `quarantine` | What happens to a row that fails: `warn` keeps it and counts it, `quarantine` keeps it out of silver in the Quarantine table, and `fail` stops the update. |
