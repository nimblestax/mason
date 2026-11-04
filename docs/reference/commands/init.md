---
title: mason init
description: Create a working project.
generated: true
mason_version: 0.1.0
---

```console
$ mason init [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--ci` | `github` | `github` | CI provider to write files for. |
| `--host` | text | `https://your-workspace.cloud.databricks.com` | Workspace URL. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `mason.init/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `project` | string | The folder the project was created in. |
