<h1 align=center><code>mason</code></h1>

<div align=center>
  <a href=https://github.com/nimblestax/mason-core/actions/workflows/ci.yml>
    <img src=https://github.com/nimblestax/mason-core/actions/workflows/ci.yml/badge.svg alt="build status">
  </a>
  <a href=LICENSE>
    <img src=https://img.shields.io/badge/license-Apache%202.0-blue.svg alt="Apache 2.0 license">
  </a>
</div>
<br>

Mason brings the software development lifecycle to Databricks pipelines: config-driven pipelines from bronze to gold, reviewed in pull requests, tested, and promoted from dev to prod.

**Status:** early development. Nothing is released, so there's nothing to install yet. The Plan shown on [nimblestax.com](https://nimblestax.com) is illustrative: Mason has no Plan command today.

A pipeline is YAML and SQL in your repo. A Source says where data lands:

```yaml
# domains/sales/sources/orders.yaml
kind: source
version: 1
path: /Volumes/{env}_sales/bronze/landing/orders
format: json
```

A Model is the SQL you'd write anyway, using Logical Names:

```sql
-- domains/sales/models/fct_orders.sql
SELECT order_id, amount
FROM sales.silver.orders
```

Mason compiles that for each Environment:

```console
$ mason compile --env dev
CREATE OR REFRESH STREAMING TABLE dev_sales.bronze.orders
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/dev_sales/bronze/landing/orders', format => 'json');
...
CREATE OR REFRESH MATERIALIZED VIEW dev_sales.gold.fct_orders AS
SELECT order_id, amount
FROM dev_sales.silver.orders
```

And it catches mistakes before anything touches a workspace:

```console
$ mason validate
MSN201 domains/sales/models/fct_orders.sql: sales.silver.ordrs isn't a table in this project.
  Fix: Declare a Source or Gold Model with this name, or correct the Logical Name.
```

## What works today

- `mason init` creates a working project, with GitHub Actions workflows.
- `mason validate` checks config and SQL references with no workspace. A Model's dependencies come from its SQL, with no list to keep: CTEs, aliases and `STREAM(...)` just work, and anything Mason can't read, such as `IDENTIFIER(...)`, is an error rather than a guess.
- `mason compile` writes generated code, or prints it for one Environment.
- `mason deploy` deploys to an Environment and refreshes its tables.
- `mason schema` prints any Kind's fields.
- Every command has [`--json` output](docs/json-output.md), rule IDs and fixed exit codes.

## The Nimblestax Way

Mason is built around an opinionated way of building on Databricks. Read the principles at [nimblestax.com/way](https://nimblestax.com/way).

## Follow progress

Watch this repo's releases on GitHub.

## License

[Apache License 2.0](LICENSE). Contributions are accepted under the [Developer Certificate of Origin](https://developercertificate.org/): sign off each commit with `git commit -s`.
