"""`${` in a Gold Model's SQL is the author's text, never a placeholder for Mason or Databricks.

Generated code refers to each Environment's names as `${key}`, and the pipeline substitutes
`${key}` anywhere in its SQL, inside strings and comments too. So `${` in the author's SQL is
written as `\\u0024{` in generated code, which keeps every string's value the same.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app

MODEL_SQL = "domains/sales/models/fct_orders.sql"
GENERATED = "build/src/sales/gold/fct_orders.sql"

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def write_model(project: Path, query: str) -> None:
    (project / MODEL_SQL).write_text(query)


def compiled(project: Path) -> tuple[str, str]:
    """The SQL printed for dev, and the same Model in the Build Package."""
    printed = mason(project, "compile", "--env", "dev")
    assert printed.exit_code == 0, printed.output
    assert mason(project, "compile").exit_code == 0
    return printed.stdout, (project / GENERATED).read_text()


def test_a_placeholder_in_a_string_compiles_as_the_same_text(project: Path):
    write_model(project, "SELECT '${env}' AS x, order_id\nFROM sales.silver.orders")

    for sql in compiled(project):
        assert r"SELECT '\u0024{env}' AS x" in sql
        assert "${env}" not in sql


def test_a_string_naming_a_setting_is_not_substituted(project: Path):
    write_model(project, "SELECT '${catalog_sales_silver}' AS x FROM sales.silver.orders")

    printed, package = compiled(project)

    assert r"'\u0024{catalog_sales_silver}'" in printed
    assert r"'\u0024{catalog_sales_silver}'" in package
    assert "FROM ${catalog_sales_silver}.${schema_sales_silver}.orders" in package


@pytest.mark.parametrize(
    "written, generated",
    [
        ('"${env}"', r'"\u0024{env}"'),
        (r"'\\${env}'", r"'\\\u0024{env}'"),
        # `\$` is already `$`, so its backslash goes, or the value would gain one.
        (r"'\${env}'", r"'\u0024{env}'"),
        (r"'\\\${env}'", r"'\\\u0024{env}'"),
        ("'a ${x} b ${y}'", r"'a \u0024{x} b \u0024{y}'"),
        ("'$ {x} ${'", r"'$ {x} \u0024{'"),
    ],
)
def test_each_string_keeps_its_value(project: Path, written: str, generated: str):
    write_model(project, f"SELECT {written} AS x FROM sales.silver.orders")

    printed, package = compiled(project)

    assert f"SELECT {generated} AS x" in printed
    assert f"SELECT {generated} AS x" in package


def test_a_placeholder_in_a_comment_is_escaped_and_the_layout_kept(project: Path):
    write_model(
        project,
        "-- Built for ${env}.\nSELECT order_id /* not ${catalog_sales_silver} */\n"
        "FROM sales.silver.orders -- ${x}\n",
    )

    printed, package = compiled(project)

    assert (
        "-- Built for \\u0024{env}.\nSELECT order_id /* not \\u0024{catalog_sales_silver} */\n"
        "FROM dev_sales.silver.orders -- \\u0024{x}\n"
    ) in printed
    assert "FROM ${catalog_sales_silver}.${schema_sales_silver}.orders -- \\u0024{x}" in package


def test_a_placeholder_in_a_hint_is_escaped(project: Path):
    write_model(project, "SELECT /*+ BROADCAST(${x}) */ order_id FROM sales.silver.orders")

    printed, _ = compiled(project)

    assert r"/*+ BROADCAST(\u0024{x}) */" in printed


def test_a_placeholder_that_is_not_in_a_string_or_comment_never_crashes_compile(project: Path):
    write_model(project, "SELECT `${env}`, ${nope} FROM sales.silver.orders")

    result = mason(project, "compile", "--env", "dev", "--json")

    assert result.exit_code == 0, result.output
    assert "SELECT `${env}`, ${nope} FROM dev_sales.silver.orders" in result.stdout


def test_a_placeholder_in_a_raw_string_fails_validate_with_its_own_rule(project: Path):
    write_model(project, "SELECT order_id,\n  r'${env}' AS x\nFROM sales.silver.orders")

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1, result.output
    [failure] = json.loads(result.stdout)["diagnostics"]
    assert failure["rule"] == "MSN207"
    assert failure["name"] == "raw-string-placeholder"
    assert failure["file"] == MODEL_SQL
    assert failure["line"] == 2
    assert "r'${env}'" in failure["message"]
    assert failure["fix"]


def test_a_raw_string_without_a_placeholder_validates(project: Path):
    write_model(project, r"SELECT r'C:\path $ {x}' AS x FROM sales.silver.orders")

    assert mason(project, "validate").exit_code == 0


def test_a_raw_string_with_a_placeholder_still_compiles_without_crashing(project: Path):
    write_model(project, "SELECT r'${env}' AS x FROM sales.silver.orders")

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
