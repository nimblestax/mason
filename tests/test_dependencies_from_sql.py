"""A Gold Model's reads come only from its SQL, and anything Mason can't read is an error."""

import json
import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason import sql
from mason.cli import app
from mason.names import LogicalName

ORDERS = LogicalName("sales", "silver", "orders")
MODEL_SQL = "domains/sales/models/fct_orders.sql"

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def write_model(project: Path, query: str) -> None:
    (project / MODEL_SQL).write_text(query)


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def test_a_cte_an_alias_and_a_stream_over_one_logical_name_are_one_read():
    query = """
        WITH recent AS (SELECT * FROM STREAM(sales.silver.orders) AS o)
        SELECT r.order_id FROM recent AS r
    """

    assert sql.reads(query) == {ORDERS}


def test_a_stream_read_compiles_to_the_real_table(project: Path):
    write_model(project, "SELECT order_id FROM STREAM(sales.silver.orders)")

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
    assert "FROM STREAM(dev_sales.silver.orders)" in result.stdout


def test_a_computed_table_name_fails_with_its_own_rule(project: Path):
    write_model(project, "SELECT *\nFROM IDENTIFIER('sales.silver.' || :entity)")

    [failure] = failures(project)

    assert failure["rule"] == "MSN204"
    assert failure["name"] == "computed-table-name"
    assert failure["file"] == MODEL_SQL
    assert failure["line"] == 2
    assert "Logical Name" in failure["fix"]


def test_sql_that_does_not_parse_fails_with_its_own_rule(project: Path):
    write_model(project, "SELECT order_id,\nFROM WHERE")

    [failure] = failures(project)

    assert failure["rule"] == "MSN203"
    assert failure["name"] == "unparseable-sql"
    assert failure["line"] == 2
    assert failure["fix"]


def test_a_second_statement_fails_rather_than_hiding_its_reads(project: Path):
    write_model(project, "SELECT * FROM sales.silver.orders;\nSELECT * FROM sales.silver.nope")

    [failure] = failures(project)

    assert failure["rule"] == "MSN203"


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("SELECT *\nFROM orders", "orders"),
        ("SELECT *\nFROM silver.orders", "silver.orders"),
        ("WITH orders AS (\nSELECT * FROM orders)\nSELECT * FROM orders", "orders"),
    ],
)
def test_a_name_that_is_neither_a_cte_nor_a_logical_name_is_unresolved(
    project: Path, query: str, name: str
):
    write_model(project, query)

    [failure] = failures(project)

    assert failure["rule"] == "MSN201"
    assert failure["line"] == 2
    assert f"`{name}`" in failure["message"]
    assert "three-part Logical Name" in failure["fix"]


def test_ordinary_sql_with_ctes_and_aliases_validates(project: Path):
    write_model(
        project,
        """
        WITH recent AS (SELECT * FROM STREAM(sales.silver.orders) AS o),
             totals AS (SELECT order_id, sum(amount) AS amount FROM recent GROUP BY order_id)
        SELECT t.order_id, t.amount FROM totals AS t JOIN recent r ON t.order_id = r.order_id
        WHERE t.order_id IN (SELECT order_id FROM recent)
        """,
    )

    result = mason(project, "validate", "--json")

    assert result.exit_code == 0, result.output


def test_a_real_table_name_fails_with_a_fix_naming_its_logical_name(project: Path):
    platform = project / "mason.platform.yaml"
    platform.write_text(
        platform.read_text().replace(
            "environments:\n", "environments:\n  prod:\n    host: https://prod.example.com\n"
        )
    )
    write_model(project, "SELECT *\nFROM prod_sales.silver.orders")

    [failure] = failures(project)

    assert failure["rule"] == "MSN205"
    assert failure["name"] == "real-table-name"
    assert failure["line"] == 2
    assert "prod_sales.silver.orders" in failure["message"]
    assert "sales.silver.orders" in failure["fix"]


NOT_QUERIES = [
    ("DROP", "DROP TABLE sales.silver.orders"),
    ("INSERT", "INSERT INTO sales.gold.dim_date SELECT * FROM sales.silver.orders"),
    ("DELETE", "DELETE FROM sales.silver.orders WHERE amount < 0"),
    ("UPDATE", "UPDATE sales.silver.orders SET amount = 0"),
    (
        "MERGE",
        "MERGE INTO sales.silver.orders AS t USING sales.bronze.orders AS s"
        " ON t.order_id = s.order_id WHEN MATCHED THEN DELETE",
    ),
    ("CREATE", "CREATE TABLE sales.gold.copy AS SELECT * FROM sales.silver.orders"),
    ("CREATE", "CREATE VIEW sales.gold.copy AS SELECT * FROM sales.silver.orders"),
    ("USE", "USE CATALOG prod_sales"),
]


@pytest.mark.parametrize(("statement", "query"), NOT_QUERIES)
def test_a_statement_that_is_not_a_query_cannot_be_parsed_as_reads(statement: str, query: str):
    with pytest.raises(sql.Unparseable, match=f"It's a {statement} statement, not a query."):
        sql.parse(query)


@pytest.mark.parametrize("query", [query for _, query in NOT_QUERIES])
def test_a_statement_that_is_not_a_query_fails_with_only_msn203(project: Path, query: str):
    write_model(project, query)

    [failure] = failures(project)

    assert failure["rule"] == "MSN203"
    assert failure["fix"] == "Make the file one Databricks SQL query that runs on its own."


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM sales.silver.orders",
        "WITH o AS (SELECT * FROM sales.silver.orders) SELECT * FROM o",
        "SELECT order_id FROM sales.silver.orders\n"
        "UNION ALL SELECT order_id FROM sales.bronze.orders",
        "(SELECT 1 AS a UNION SELECT 2) EXCEPT SELECT 3",
        "VALUES (1, 'a'), (2, 'b')",
        "SELECT * FROM sales.silver.orders;",
    ],
)
def test_every_kind_of_query_validates(project: Path, query: str):
    write_model(project, query)

    result = mason(project, "validate", "--json")

    assert result.exit_code == 0, result.output


JOINED = "FROM sales.silver.orders o\nJOIN sales.bronze.orders c USING (order_id)"


@pytest.mark.parametrize(
    "hint",
    [
        "/*+ BROADCAST(c) */",
        "/*+ MERGE(o, c) */",
        "/*+ SHUFFLE_HASH(c) */",
        "/*+ BROADCASTJOIN(c) */",
        "/*+ MAPJOIN(c) */",
        "/*+ BROADCAST(nope) */",
        "/*+ REPARTITION(4) */",
        "/*+ COALESCE(1) */",
    ],
)
def test_a_hint_is_never_a_read_and_compiles_unchanged(project: Path, hint: str):
    query = f"SELECT {hint} o.order_id\n{JOINED}"
    write_model(project, query)

    assert sql.reads(query) == {ORDERS, LogicalName("sales", "bronze", "orders")}
    assert mason(project, "validate", "--json").exit_code == 0
    compiled = mason(project, "compile", "--env", "dev")
    assert compiled.exit_code == 0, compiled.output
    assert hint in compiled.stdout


def test_a_hint_naming_a_cte_validates(project: Path):
    write_model(
        project,
        "WITH recent AS (SELECT * FROM sales.silver.orders)\n"
        "SELECT /*+ BROADCAST(recent) */ * FROM sales.bronze.orders JOIN recent USING (order_id)",
    )

    assert mason(project, "validate", "--json").exit_code == 0


def test_a_logical_name_in_a_hint_compiles_like_the_join_it_names(project: Path):
    write_model(
        project,
        "SELECT /*+ BROADCAST(sales.bronze.orders) */ o.order_id -- sales.bronze.orders\n"
        "FROM sales.silver.orders o JOIN sales.bronze.orders USING (order_id)\n"
        "WHERE o.note <> 'sales.bronze.orders'",
    )

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
    assert "/*+ BROADCAST(dev_sales.bronze.orders) */" in result.stdout
    assert "JOIN dev_sales.bronze.orders USING" in result.stdout
    assert "-- sales.bronze.orders" in result.stdout
    assert "'sales.bronze.orders'" in result.stdout


def test_a_hint_does_not_hide_a_bad_read(project: Path):
    write_model(project, "SELECT /*+ BROADCAST(o) */ *\nFROM sales.silver.ordrs o")

    [failure] = failures(project)

    assert failure["rule"] == "MSN201"
    assert "sales.silver.ordrs" in failure["message"]


def test_broken_hint_syntax_is_ignored_like_any_hint(project: Path):
    write_model(project, f"SELECT /*+ BROADCAST(c */ o.order_id\n{JOINED}")

    result = mason(project, "validate", "--json")

    assert result.exit_code == 0, result.output


def add_environment(project: Path, env: str) -> None:
    platform = project / "mason.platform.yaml"
    platform.write_text(
        platform.read_text().replace(
            "environments:\n", f"environments:\n  {env}:\n    host: https://{env}.example.com\n"
        )
    )


def compiles_in_every_environment(project: Path) -> list[str]:
    outputs = []
    for env in ("dev", "prod"):
        result = mason(project, "compile", "--env", env)
        assert result.exit_code == 0, result.output
        outputs.append(result.stdout)
    assert mason(project, "compile").exit_code == 0
    return outputs


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM Sales.Silver.Orders",
        "SELECT * FROM sales.silver.Orders",
        "SELECT * FROM STREAM(Sales.Silver.Orders)",
        "WITH Paid AS (SELECT * FROM sales.silver.orders) SELECT * FROM paid",
    ],
)
def test_names_match_whatever_their_case(project: Path, query: str):
    add_environment(project, "prod")
    write_model(project, query)

    assert sql.reads(query) == {ORDERS}
    assert mason(project, "validate", "--json").exit_code == 0
    dev, prod = compiles_in_every_environment(project)
    assert "dev_sales.silver.orders" in dev
    assert "prod_sales.silver.orders" in prod


def test_a_source_file_with_capitals_is_read_in_lowercase(project: Path):
    add_environment(project, "prod")
    sources = project / "domains/sales/sources"
    (sources / "orders.yaml").rename(sources / "Orders.yaml")

    assert mason(project, "validate", "--json").exit_code == 0, failures(project)
    compiles_in_every_environment(project)


def test_a_domain_with_capitals_is_read_in_lowercase(project: Path):
    add_environment(project, "prod")
    platform = project / "mason.platform.yaml"
    platform.write_text(platform.read_text().replace("  - sales\n", "  - Sales\n"))
    (project / "domains/sales").rename(project / "domains/Sales")

    assert mason(project, "validate", "--json").exit_code == 0, failures(project)
    dev, prod = compiles_in_every_environment(project)
    assert "dev_Sales.silver.orders" in dev
    assert "prod_Sales.silver.orders" in prod
    bundle = (project / "build/databricks.yml").read_text()
    declared = set(yaml.safe_load(bundle)["variables"])
    assert set(re.findall(r"\$\{var\.(\w+)\}", bundle)) <= declared


def test_a_real_table_name_in_capitals_points_to_its_logical_name(project: Path):
    add_environment(project, "prod")
    write_model(project, "SELECT * FROM PROD_SALES.silver.orders")

    [failure] = failures(project)

    assert failure["rule"] == "MSN205"
    assert "PROD_SALES.silver.orders is a real table name" in failure["message"]
    assert "sales.silver.orders" in failure["fix"]


def test_a_typo_in_capitals_is_still_unresolved(project: Path):
    write_model(project, "SELECT * FROM Sales.Silver.Ordrs")

    [failure] = failures(project)

    assert failure["rule"] == "MSN201"
    assert "Sales.Silver.Ordrs" in failure["message"]


def test_a_cte_body_reading_its_own_name_in_another_case_is_unresolved(project: Path):
    write_model(project, "WITH Orders AS (\nSELECT * FROM orders)\nSELECT * FROM ORDERS")

    [failure] = failures(project)

    assert failure["rule"] == "MSN201"
    assert failure["line"] == 2


def test_one_table_in_two_cases_is_one_read_and_one_typo_is_reported_once(project: Path):
    query = "SELECT * FROM sales.silver.orders JOIN SALES.SILVER.ORDERS USING (order_id)"
    assert sql.reads(query) == {ORDERS}

    write_model(project, "SELECT * FROM sales.silver.ordrs JOIN Sales.Silver.ORDRS USING (id)")
    [failure] = failures(project)
    assert failure["rule"] == "MSN201"
