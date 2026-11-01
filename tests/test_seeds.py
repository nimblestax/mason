"""A Seed: reference data kept in Git, checked against its schema and replaced on each deploy."""

import json
from pathlib import Path

import pytest
import sqlglot
import yaml
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()

SEEDS = "domains/sales/seeds"
COMPILED = "build/src/sales/ingest/countries.sql"
CONFIG = """kind: seed
version: 1
file: countries.csv
columns:
  code: STRING
  vat_rate: DECIMAL(4, 2)
"""


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    (tmp_path / SEEDS).mkdir()
    return tmp_path


def declare_seed(project: Path, csv: str, config: str = CONFIG) -> None:
    (project / SEEDS / "countries.yaml").write_text(config)
    (project / SEEDS / "countries.csv").write_text(csv)


def compiled(project: Path) -> str:
    result = mason(project, "compile")
    assert result.exit_code == 0, result.output
    return (project / COMPILED).read_text()


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def test_a_valid_seed_validates_and_lands_in_its_domains_silver(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\nNZ,0.15\n")

    assert mason(project, "validate").exit_code == 0

    code = compiled(project)
    assert (
        "CREATE OR REFRESH MATERIALIZED VIEW "
        "${catalog_sales_silver}.${schema_sales_silver}.countries" in code
    )
    assert "CAST(`vat_rate` AS DECIMAL(4, 2)) AS `vat_rate`" in code
    assert "('AU', '0.10')" in code
    assert "('NZ', '0.15')" in code


def test_a_row_that_doesnt_match_the_declared_schema_fails_validate(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\nNZ,lots\n")

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "seed-row-mismatch"
    assert diagnostic["file"] == f"{SEEDS}/countries.csv"
    assert diagnostic["line"] == 3
    assert "vat_rate" in diagnostic["message"]
    assert "DECIMAL(4, 2)" in diagnostic["message"]


def test_a_gold_model_reads_a_seed_through_a_logical_name(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\n")
    gold = project / "domains/sales/models/fct_orders.sql"
    gold.write_text("SELECT code FROM sales.silver.countries\n")

    assert mason(project, "validate").exit_code == 0

    mason(project, "compile")
    assert (
        "FROM ${catalog_sales_silver}.${schema_sales_silver}.countries"
        in (project / "build/src/sales/gold/fct_orders.sql").read_text()
    )


def test_a_seed_has_no_bronze_table(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\n")
    gold = project / "domains/sales/models/fct_orders.sql"
    gold.write_text("SELECT code FROM sales.bronze.countries\n")

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "unresolved-logical-name"


def test_a_domain_with_only_seeds_still_gets_a_pipeline_that_runs_before_gold(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\n")
    (project / "domains/sales/sources/orders.yaml").unlink()
    gold = project / "domains/sales/models/fct_orders.sql"
    gold.write_text("SELECT code FROM sales.silver.countries\n")

    assert mason(project, "compile").exit_code == 0

    bundle = yaml.safe_load((project / "build/databricks.yml").read_text())
    assert "sales_ingest" in bundle["resources"]["pipelines"]
    tasks = {t["task_key"]: t for t in bundle["resources"]["jobs"]["refresh"]["tasks"]}
    assert tasks["sales_gold"]["depends_on"] == [{"task_key": "sales_ingest"}]


def test_removing_a_row_from_the_file_removes_it_from_the_generated_table(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\nNZ,0.15\n")
    before = compiled(project)
    declare_seed(project, "code,vat_rate\nAU,0.10\n")

    after = compiled(project)

    assert "'NZ'" in before
    assert "'NZ'" not in after
    assert "'AU'" in after


@pytest.mark.parametrize(
    ("sql_type", "value"),
    [
        ("TINYINT", "128"),
        ("SMALLINT", "32768"),
        ("INT", "2147483648"),
        ("INTEGER", "1.5"),
        ("BIGINT", "9223372036854775808"),
        ("BOOLEAN", "maybe"),
        ("FLOAT", "nan"),
        ("DOUBLE", "1_000"),
        ("DECIMAL(4, 2)", "123.45"),
        ("DECIMAL(4, 2)", "1.234"),
        ("DECIMAL(4)", "1.5"),
        ("DECIMAL", "12345678901"),
        ("DATE", "2026-02-30"),
        ("DATE", "20260201"),
        ("TIMESTAMP", "2026-02-01"),
        ("TIMESTAMP_NTZ", "2026-02-01T10:00:00+10:00"),
    ],
)
def test_a_value_outside_its_declared_type_is_rejected(project: Path, sql_type: str, value: str):
    config = f"kind: seed\nversion: 1\nfile: countries.csv\ncolumns:\n  value: {sql_type}\n"
    declare_seed(project, f"value\n{value}\n", config)

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "seed-row-mismatch"
    assert diagnostic["line"] == 2


@pytest.mark.parametrize(
    ("sql_type", "value"),
    [
        ("tinyint", "-128"),
        ("INT", "+5"),
        ("BIGINT", "9223372036854775807"),
        ("BOOLEAN", "TRUE"),
        ("DOUBLE", "-1.5e3"),
        ("DECIMAL(4, 2)", "12.34"),
        ("DECIMAL(4, 2)", ".5"),
        ("DECIMAL", "1234567890"),
        ("DATE", "2026-02-28"),
        ("TIMESTAMP", "2026-02-01 10:00:00"),
        ("TIMESTAMP", "2026-02-01T10:00:00.123+10:00"),
        ("TIMESTAMP_NTZ", "2026-02-01 10:00:00"),
    ],
)
def test_a_value_within_its_declared_type_is_accepted(project: Path, sql_type: str, value: str):
    config = f"kind: seed\nversion: 1\nfile: countries.csv\ncolumns:\n  value: {sql_type}\n"
    declare_seed(project, f"value\n{value}\n", config)

    result = mason(project, "validate")

    assert result.exit_code == 0, result.output


def test_a_type_mason_cant_check_fails_validate_and_names_the_ones_it_can(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\n", CONFIG.replace("STRING", "VARCAHR"))

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "unsupported-seed-type"
    assert diagnostic["file"] == f"{SEEDS}/countries.yaml"
    assert "VARCAHR" in diagnostic["message"]
    assert "TIMESTAMP_NTZ" in diagnostic["fix"]


def test_a_data_file_that_doesnt_exist_fails_validate(project: Path):
    declare_seed(project, "")
    (project / SEEDS / "countries.csv").unlink()

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "missing-seed-file"
    assert diagnostic["file"] == f"{SEEDS}/countries.yaml"


@pytest.mark.parametrize(
    ("csv", "named"),
    [
        ("", "code"),
        ("code\nAU\n", "vat_rate"),
        ("code,vat_rate,extra\nAU,0.10,x\n", "extra"),
        ("code,code\nAU,AU\n", "code"),
    ],
)
def test_a_header_that_doesnt_match_the_columns_fails_validate(project: Path, csv: str, named: str):
    declare_seed(project, csv)

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "seed-header-mismatch"
    assert diagnostic["file"] == f"{SEEDS}/countries.csv"
    assert diagnostic["line"] == 1
    assert named in diagnostic["message"]


@pytest.mark.parametrize("row", ["AU", "AU,0.10,extra"])
def test_a_row_with_the_wrong_number_of_values_fails_validate(project: Path, row: str):
    declare_seed(project, f"code,vat_rate\nNZ,0.15\n{row}\n")

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "seed-row-mismatch"
    assert diagnostic["line"] == 3


@pytest.mark.parametrize("content", [b'code,vat_rate\n"AU,0.10\n', b"code,vat_rate\n\xff,0.10\n"])
def test_a_data_file_that_cant_be_read_fails_validate(project: Path, content: bytes):
    declare_seed(project, "")
    (project / SEEDS / "countries.csv").write_bytes(content)

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "unreadable-config"
    assert diagnostic["file"] == f"{SEEDS}/countries.csv"


def test_a_column_name_that_isnt_an_identifier_fails_validate(project: Path):
    declare_seed(project, "code,vat`rate\nAU,0.10\n", CONFIG.replace("vat_rate", '"vat`rate"'))

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "invalid-field"


def test_a_seed_and_a_source_with_one_name_are_one_table_and_fail_validate(project: Path):
    declare_seed(project, "code,vat_rate\nAU,0.10\n")
    (project / SEEDS / "countries.yaml").rename(project / SEEDS / "orders.yaml")

    [diagnostic] = failures(project)

    assert diagnostic["name"] == "duplicate-table"
    assert diagnostic["file"] == f"{SEEDS}/orders.yaml"
    assert "sales.silver.orders" in diagnostic["message"]


def test_columns_can_sit_in_any_order_in_the_file(project: Path):
    declare_seed(project, "vat_rate,code\n0.10,AU\n")

    assert "('AU', '0.10')" in compiled(project)


def test_a_data_file_saved_with_a_byte_order_mark_is_read(project: Path):
    declare_seed(project, "﻿code,vat_rate\nAU,0.10\n")

    assert "('AU', '0.10')" in compiled(project)


def test_an_empty_value_is_null_in_every_type(project: Path):
    declare_seed(project, "code,vat_rate\nAU,\n,0.15\n")

    code = compiled(project)

    assert "('AU', NULL)" in code
    assert "(NULL, '0.15')" in code


def test_a_seed_with_every_row_removed_is_an_empty_table_with_its_columns(project: Path):
    declare_seed(project, "code,vat_rate\n")

    code = compiled(project)

    assert "CAST(`code` AS STRING) AS `code`" in code
    assert "(NULL, NULL)" in code
    assert code.rstrip().endswith("WHERE false;")


@pytest.mark.parametrize(
    ("value", "literal"),
    [
        ("O'Brien", r"'O\'Brien'"),
        (r"back\slash", r"'back\\slash'"),
        ("${price}", r"'\u0024{price}'"),
    ],
)
def test_values_stay_literal_in_generated_sql(project: Path, value: str, literal: str):
    declare_seed(project, f"code,vat_rate\n{value},0.10\n")

    assert f"({literal}, '0.10')" in compiled(project)


def test_a_value_that_looks_like_a_placeholder_prints_for_an_environment(project: Path):
    declare_seed(project, "code,vat_rate\n${price},0.10\n")

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output


def test_generated_sql_parses_for_a_row_needing_every_kind_of_escape(project: Path):
    declare_seed(project, "code,vat_rate\nO'Brien\\${x},0.10\n,\n")

    statement = compiled(project).split("\n", 1)[1].removeprefix("AS ").rstrip(";\n")

    sqlglot.parse_one(statement, dialect="databricks")
