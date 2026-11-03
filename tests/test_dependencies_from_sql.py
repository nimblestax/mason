"""A Gold Model's reads come only from its SQL, and anything Mason can't read is an error."""

import json
from pathlib import Path

import pytest
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
