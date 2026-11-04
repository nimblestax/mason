---
title: mason deploy
description: Deploy to an Environment and refresh its tables.
generated: true
mason_version: 0.1.0
---

```console
$ mason deploy [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--env` | text | Required | The Environment to deploy. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `mason.deploy/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `env` | string | The Environment deployed and refreshed. |
