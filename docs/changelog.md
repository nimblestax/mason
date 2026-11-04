---
title: Changelog
description: What changed in each release of Mason, newest first.
---

Every release of Mason, newest first. Each section is also that release's notes on GitHub.

Mason follows [Semantic Versioning](https://semver.org). Before 1.0, a minor release, such as 0.2.0, may change config or commands in ways that need edits to your project, and its section here says what to change. A patch release, such as 0.2.1, never does.

## 0.1.0

The first release. Install it into your project with `uv add --dev mason-databricks`.

- `mason init` creates a working project, with GitHub Actions workflows.
- `mason validate` checks config and SQL with no workspace. A Model's dependencies come from its SQL, and anything Mason can't read, such as `IDENTIFIER(...)`, is an error rather than a guess.
- `mason compile` writes the generated code, or prints it for one Environment.
- `mason deploy` deploys to an Environment and refreshes its tables. When a refresh fails, it says why.
- `mason schema` prints any Kind's fields.
- A Source lands in bronze, and silver either appends it or upserts it by `keys` and `sequence_by`, with Type 1 or Type 2 history and `delete_when` for deletes.
- Seeds load small reference tables from CSV files in the repo.
- Expectations check silver rows, and rows that fail are kept in Quarantine.
- Every command has `--json` output, with rule IDs and fixed exit codes, and each rule has its own reference page.
