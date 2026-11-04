---
title: mason validate
description: Check config and SQL references, with no workspace.
generated: true
mason_version: 0.1.0
---

```console
$ mason validate [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `mason.validate/1`. When it succeeds, `result` is:

Empty: `validate` reports what it finds as diagnostics.
