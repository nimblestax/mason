"""Expectations on a Source's silver, and the Quarantine that keeps the rows they turn away."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()

SOURCE = "domains/sales/sources/orders.yaml"
BRONZE_TABLE = "${catalog_sales_bronze}.${schema_sales_bronze}.orders"
SILVER_TABLE = "${catalog_sales_silver}.${schema_sales_silver}.orders"
QUARANTINE_TABLE = "${catalog_sales_silver}.${schema_sales_silver}.orders_quarantine"


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def declare_silver(project: Path, block: str) -> None:
    path = project / SOURCE
    path.write_text(path.read_text() + block)


def generated(project: Path) -> str:
    result = mason(project, "compile")
    assert result.exit_code == 0, result.output
    return (project / "build/src/sales/ingest/orders.sql").read_text()


def test_a_quarantining_expectation_routes_failing_rows_to_quarantine_with_the_reason(
    project: Path,
):
    declare_silver(
        project,
        "silver:\n"
        "  expectations:\n"
        "    - name: positive_amount\n"
        "      expect: amount > 0\n"
        "      action: quarantine\n",
    )

    code = generated(project)

    assert f"""CREATE OR REFRESH STREAMING TABLE {SILVER_TABLE}
AS SELECT *
FROM STREAM({BRONZE_TABLE})
WHERE coalesce(amount > 0, false);
""" in code
    assert f"""CREATE OR REFRESH STREAMING TABLE {QUARANTINE_TABLE}
AS SELECT
  *,
  concat_ws(', ',
    IF(coalesce(amount > 0, false), NULL, 'positive_amount')
  ) AS _quarantine_reason
FROM STREAM({BRONZE_TABLE})
WHERE NOT (coalesce(amount > 0, false));
""" in code
    assert "mason" not in code.lower()


def test_quarantine_is_the_default_action(project: Path):
    declare_silver(
        project, "silver:\n  expectations:\n    - name: has_id\n      expect: id IS NOT NULL\n"
    )

    code = generated(project)

    assert "WHERE coalesce(id IS NOT NULL, false);\n" in code
    assert f"CREATE OR REFRESH STREAMING TABLE {QUARANTINE_TABLE}\n" in code


def test_warn_and_fail_compile_to_constraints_on_silver_and_no_quarantine(project: Path):
    declare_silver(
        project,
        "silver:\n"
        "  expectations:\n"
        "    - name: known_status\n"
        "      expect: status IN ('open', 'closed')\n"
        "      action: warn\n"
        "    - name: has_id\n"
        "      expect: id IS NOT NULL\n"
        "      action: fail\n",
    )

    code = generated(project)

    assert f"""CREATE OR REFRESH STREAMING TABLE {SILVER_TABLE} (
  CONSTRAINT known_status EXPECT (coalesce(status IN ('open', 'closed'), false)),
  CONSTRAINT has_id EXPECT (coalesce(id IS NOT NULL, false)) ON VIOLATION FAIL UPDATE
)
AS SELECT *
FROM STREAM({BRONZE_TABLE});
""" in code
    assert "_quarantine" not in code


def test_an_upsert_reads_only_passing_rows_through_a_view_so_quarantined_changes_never_reach_silver(
    project: Path,
):
    declare_silver(
        project,
        "silver:\n"
        "  keys: [order_id]\n"
        "  sequence_by: updated_at\n"
        "  expectations:\n"
        "    - name: positive_amount\n"
        "      expect: amount > 0\n"
        "    - name: known_status\n"
        "      expect: status IN ('open', 'closed')\n"
        "      action: warn\n",
    )

    code = generated(project)

    assert f"""CREATE OR REFRESH STREAMING TABLE {SILVER_TABLE};

CREATE TEMPORARY VIEW conformed_orders (
  CONSTRAINT known_status EXPECT (coalesce(status IN ('open', 'closed'), false))
)
AS SELECT *
FROM STREAM({BRONZE_TABLE})
WHERE coalesce(amount > 0, false);

CREATE FLOW upsert_orders AS AUTO CDC INTO {SILVER_TABLE}
FROM STREAM(conformed_orders)
KEYS (order_id)
""" in code
    assert f"FROM STREAM({BRONZE_TABLE})\nWHERE NOT (coalesce(amount > 0, false));\n" in code


def test_an_upsert_with_no_expectations_still_reads_bronze_directly(project: Path):
    declare_silver(project, "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n")

    code = generated(project)

    assert f"AUTO CDC INTO {SILVER_TABLE}\nFROM STREAM({BRONZE_TABLE})\n" in code
    assert "VIEW" not in code


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


@pytest.mark.parametrize(
    "condition",
    [
        "amount >",  # doesn't parse
        "amount > 0; DROP TABLE x",  # two statements
        "SELECT 1",  # a query, not a condition
        "amount > (SELECT avg(amount) FROM x)",  # reads other rows
        "id IN (SELECT id FROM x)",  # a subquery with no aggregate
        "amount > avg(amount)",  # an aggregate
        "row_number() OVER (ORDER BY id) = 1",  # a window
        "amount > 0 -- positive",  # a comment would swallow the rest of the generated line
    ],
)
def test_an_expectation_that_isnt_a_condition_on_one_row_fails_validation_with_a_rule_id(
    project: Path, condition: str
):
    declare_silver(
        project,
        f"silver:\n  expectations:\n    - name: bad\n      expect: {json.dumps(condition)}\n",
    )

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN116"
    assert diagnostic["file"] == SOURCE
    assert "`bad`" in diagnostic["message"]


@pytest.mark.parametrize(
    "rule",
    [
        "    - name: Bad Name\n      expect: id > 0\n",
        "    - name: ok\n      expect: id > 0\n      action: drop\n",
        "    - name: ok\n",
        "    - name: ok\n      expect: id > 0\n    - name: ok\n      expect: id < 9\n",
    ],
)
def test_a_malformed_expectation_fails_against_the_schema(project: Path, rule: str):
    declare_silver(project, f"silver:\n  expectations:\n{rule}")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"


def test_every_environment_runs_the_same_checks_against_its_own_tables(project: Path):
    declare_silver(
        project,
        "silver:\n  expectations:\n    - name: positive_amount\n      expect: amount > 0\n",
    )
    platform = project / "mason.platform.yaml"
    platform.write_text(
        platform.read_text().replace(
            "environments:\n",
            "environments:\n  prod:\n    host: https://prod.example.cloud.databricks.com\n",
        )
    )
    printed = {}
    for env in ("dev", "prod"):
        result = mason(project, "compile", "--env", env)
        assert result.exit_code == 0, result.output
        printed[env] = result.stdout

    quarantine = "CREATE OR REFRESH STREAMING TABLE prod_sales.silver.orders_quarantine\n"
    assert quarantine in printed["prod"]
    assert printed["dev"].replace("dev_", "prod_").replace("/dev/", "/prod/") == printed["prod"]


def test_a_gold_model_may_read_a_quarantine_table_by_logical_name(project: Path):
    declare_silver(
        project,
        "silver:\n  expectations:\n    - name: positive_amount\n      expect: amount > 0\n",
    )
    model = project / "domains/sales/models/fct_orders.sql"
    model.write_text("SELECT * FROM sales.silver.orders_quarantine")

    assert mason(project, "validate").exit_code == 0, mason(project, "validate").output


@pytest.mark.parametrize("kind", ["source", "seed"])
def test_a_table_named_like_a_quarantine_table_fails_validation_with_a_rule_id(
    project: Path, kind: str
):
    declare_silver(
        project,
        "silver:\n  expectations:\n    - name: positive_amount\n      expect: amount > 0\n",
    )
    if kind == "source":
        clash = project / "domains/sales/sources/orders_quarantine.yaml"
        clash.write_text("kind: source\nversion: 1\npath: /Volumes/x\nformat: json\n")
    else:
        folder = project / "domains/sales/seeds"
        folder.mkdir()
        clash = folder / "orders_quarantine.yaml"
        clash.write_text(
            "kind: seed\nversion: 1\nfile: orders_quarantine.csv\ncolumns:\n  a: INT\n"
        )
        (folder / "orders_quarantine.csv").write_text("a\n1\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN202"
    assert diagnostic["file"] == clash.relative_to(project).as_posix()
    assert "Quarantine" in diagnostic["message"]


def test_schema_tells_a_person_silver_takes_expectations():
    described = runner.invoke(app, ["schema", "source"]).stdout

    assert "`expectations`" in described
