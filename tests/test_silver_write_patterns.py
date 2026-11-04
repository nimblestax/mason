"""How a Source's `silver:` block decides the way silver is written."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app
from mason.kinds.source import _delete_when

runner = CliRunner()

SOURCE = "domains/sales/sources/orders.yaml"
BRONZE_TABLE = "${catalog_sales_bronze}.${schema_sales_bronze}.orders"
SILVER_TABLE = "${catalog_sales_silver}.${schema_sales_silver}.orders"


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def declare_silver(project: Path, block: str) -> None:
    path = project / SOURCE
    path.write_text(path.read_text() + block)


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def generated(project: Path) -> str:
    result = mason(project, "compile")
    assert result.exit_code == 0, result.output
    return (project / "build/src/sales/ingest/orders.sql").read_text()


def test_keys_sequence_by_and_scd_2_generate_an_auto_cdc_flow_from_bronze(project: Path):
    declare_silver(
        project,
        "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n  scd: 2\n",
    )

    assert f"""CREATE OR REFRESH STREAMING TABLE {SILVER_TABLE};

CREATE FLOW upsert_orders AS AUTO CDC INTO {SILVER_TABLE}
FROM STREAM({BRONZE_TABLE})
KEYS (order_id)
SEQUENCE BY updated_at
STORED AS SCD TYPE 2;
""" in generated(project)


def test_scd_defaults_to_type_1(project: Path):
    declare_silver(project, "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n")

    assert "STORED AS SCD TYPE 1;" in generated(project)


def test_several_keys_are_listed_in_the_order_declared(project: Path):
    declare_silver(project, "silver:\n  keys: [region, order_id]\n  sequence_by: updated_at\n")

    assert "KEYS (region, order_id)\n" in generated(project)


@pytest.mark.parametrize("block", ["", "silver: {}\n"])
def test_a_source_with_no_keys_stays_an_append_streaming_table(project: Path, block: str):
    declare_silver(project, block)

    code = generated(project)

    assert f"CREATE OR REFRESH STREAMING TABLE {SILVER_TABLE}\nAS SELECT *\n" in code
    assert f"FROM STREAM({BRONZE_TABLE});\n" in code
    assert "AUTO CDC" not in code


def test_delete_when_compiles_to_apply_as_delete_when_before_the_sequence(project: Path):
    declare_silver(
        project,
        "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n  delete_when: \"op = 'D'\"\n",
    )

    assert "KEYS (order_id)\nAPPLY AS DELETE WHEN op = 'D'\nSEQUENCE BY updated_at\n" in generated(
        project
    )


def test_keys_without_sequence_by_fail_validation_with_a_rule_id(project: Path):
    declare_silver(project, "silver:\n  keys: [order_id]\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN110"
    assert diagnostic["file"] == SOURCE
    assert "sequence_by" in diagnostic["fix"]


@pytest.mark.parametrize(
    ("field", "block"),
    [
        ("sequence_by", "  sequence_by: updated_at\n"),
        ("scd", "  scd: 2\n"),
        ("delete_when", "  delete_when: op = 'D'\n"),
    ],
)
def test_an_upsert_field_without_keys_fails_validation_with_a_rule_id(
    project: Path, field: str, block: str
):
    declare_silver(project, f"silver:\n{block}")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN111"
    assert diagnostic["file"] == SOURCE
    assert f"`silver.{field}`" in diagnostic["message"]


def test_every_upsert_field_without_keys_is_reported_at_once(project: Path):
    declare_silver(project, "silver:\n  sequence_by: updated_at\n  scd: 2\n")

    assert [d["rule"] for d in failures(project)] == ["MSN111", "MSN111"]


@pytest.mark.parametrize(
    "block",
    [
        "  keys: []\n  sequence_by: updated_at\n",
        "  keys: order_id\n  sequence_by: updated_at\n",
        "  keys: [order_id, order_id]\n  sequence_by: updated_at\n",
        "  keys: [order_id]\n  sequence_by: updated_at\n  scd: 3\n",
        "  keys: [order_id]\n  sequence_by: updated_at\n  scd: true\n",
        "  keys: [order_id]\n  sequence_by: updated_at\n  mode: upsert\n",
    ],
)
def test_a_malformed_silver_block_fails_against_the_schema(project: Path, block: str):
    declare_silver(project, f"silver:\n{block}")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"


def test_compile_stops_on_an_invalid_combination(project: Path):
    declare_silver(project, "silver:\n  keys: [order_id]\n")

    result = mason(project, "compile")

    assert result.exit_code == 1
    assert "MSN110" in result.stdout


def test_compile_for_an_environment_shows_the_upsert_in_runnable_sql(project: Path):
    declare_silver(project, "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n")

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
    assert "AUTO CDC INTO dev_sales.silver.orders\n" in result.stdout
    assert "FROM STREAM(dev_sales.bronze.orders)\n" in result.stdout
    assert "${" not in result.stdout


def test_a_valid_upsert_passes_validation(project: Path):
    declare_silver(project, "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n  scd: 2\n")

    assert mason(project, "validate").exit_code == 0


def test_schema_names_the_fields_of_the_silver_block_for_a_person():
    described = runner.invoke(app, ["schema", "source"]).stdout

    for field in ("keys", "sequence_by", "scd", "delete_when"):
        assert f"`{field}`" in described


def test_delete_when_is_a_line_only_when_a_condition_is_given():
    assert _delete_when(None) is None
    assert _delete_when("op = 'D'") == "APPLY AS DELETE WHEN op = 'D'"


UPSERT = "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n"


def test_a_delete_when_that_would_break_the_generated_flow_fails_validation(project: Path):
    declare_silver(project, UPSERT + "  delete_when: \"op = 'D' SEQUENCE BY x\"\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN118"
    assert diagnostic["file"] == SOURCE
    assert "`silver.delete_when`" in diagnostic["message"]


@pytest.mark.parametrize(
    ("condition", "reason"),
    [
        ("op =", "doesn't parse"),
        ("op = 'D'; DROP TABLE x", "statements"),
        ("op IN (SELECT op FROM x)", "query"),
        ("count(op) > 1", "aggregate"),
        ("row_number() OVER (ORDER BY id) = 1", "window"),
        ("op = 'D' -- a delete", "comment"),
        ("op = 'D' deleted", "names its result"),
    ],
)
def test_a_delete_when_that_isnt_one_condition_on_one_row_says_why(
    project: Path, condition: str, reason: str
):
    declare_silver(project, UPSERT + f"  delete_when: {json.dumps(condition)}\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN118"
    assert reason in diagnostic["message"]
    assert diagnostic["fix"]


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("updated_at SEQUENCE BY x", "doesn't parse"),
        ("updated_at, seq", "doesn't parse"),
        ("updated_at; DROP TABLE x", "statements"),
        ("(SELECT max(updated_at) FROM x)", "query"),
        ("max(updated_at)", "aggregate"),
        ("row_number() OVER (ORDER BY updated_at)", "window"),
        ("updated_at -- the change time", "comment"),
        ("updated_at DESC", "names its result"),
    ],
)
def test_a_sequence_by_that_isnt_one_expression_on_one_row_fails_validation(
    project: Path, expression: str, reason: str
):
    declare_silver(
        project, f"silver:\n  keys: [order_id]\n  sequence_by: {json.dumps(expression)}\n"
    )

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN119"
    assert diagnostic["file"] == SOURCE
    assert "`silver.sequence_by`" in diagnostic["message"]
    assert reason in diagnostic["message"]


@pytest.mark.parametrize("expression", ["updated_at", "struct(updated_at, seq)", "ts.updated_at"])
def test_a_sequence_by_may_be_a_column_or_an_expression_on_one_row(project: Path, expression: str):
    declare_silver(project, f"silver:\n  keys: [order_id]\n  sequence_by: {expression}\n")

    assert f"SEQUENCE BY {expression}\n" in generated(project)


@pytest.mark.parametrize("key", ["order id", "order_id)", "upper(order_id)", "1st", "`order_id`"])
def test_a_key_that_isnt_a_column_name_fails_against_the_schema(project: Path, key: str):
    declare_silver(project, f"silver:\n  keys: [{json.dumps(key)}]\n  sequence_by: updated_at\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"
    assert "silver.keys" in diagnostic["message"]
