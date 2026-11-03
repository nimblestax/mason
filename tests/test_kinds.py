"""`kind` and `version` on every file, and the JSON Schemas behind them."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()

SOURCE = "domains/sales/sources/orders.yaml"
MODEL = "domains/sales/models/fct_orders.yaml"
PLATFORM = "mason.platform.yaml"
MODELINE = "# yaml-language-server: $schema="


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def edit(project: Path, file: str, old: str, new: str) -> None:
    path = project / file
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    return envelope["diagnostics"]


def test_schema_prints_a_kinds_json_schema_with_no_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["schema", "source", "--json"])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == "mason.schema/1"
    assert envelope["ok"] is True
    assert envelope["result"]["kind"] == "source"
    assert envelope["result"]["version"] == 1
    assert "path" in envelope["result"]["json_schema"]["properties"]


@pytest.mark.parametrize("kind", ["source", "seed", "model", "platform"])
def test_every_kind_has_a_schema_that_requires_kind_and_version(kind: str):
    result = runner.invoke(app, ["schema", kind, "--json"])

    assert result.exit_code == 0, result.output
    json_schema = json.loads(result.stdout)["result"]["json_schema"]
    assert {"kind", "version"} <= set(json_schema["required"])
    assert json_schema["properties"]["kind"]["const"] == kind
    assert json_schema["properties"]["kind"]["description"] == "The Kind of this file."
    Draft202012Validator.check_schema(json_schema)


def test_schema_without_json_lists_the_fields_for_a_person():
    result = runner.invoke(app, ["schema", "source"])

    assert result.exit_code == 0, result.output
    assert "source, version 1" in result.stdout
    assert "path (required)" in result.stdout
    assert "Where the files land" in result.stdout


def test_schema_of_an_unknown_kind_is_a_usage_error_that_names_the_kinds():
    result = runner.invoke(app, ["schema", "sauce", "--json"])

    assert result.exit_code == 2
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN102"
    assert "model, platform, seed, source" in diagnostic["fix"]


def test_a_file_with_no_kind_fails_validation_with_a_stated_fix(project: Path):
    edit(project, SOURCE, "kind: source\n", "")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN101"
    assert diagnostic["file"] == SOURCE
    assert "kind: source" in diagnostic["fix"]


@pytest.mark.parametrize(
    ("old", "new", "rule"),
    [
        ("kind: source\n", "kind: sauce\n", "MSN102"),
        ("kind: source\n", "kind: [source]\n", "MSN102"),
        ("kind: source\n", "kind: model\n", "MSN105"),
        ("version: 1\n", "", "MSN103"),
        ("version: 1\n", "version: 2\n", "MSN104"),
        ("version: 1\n", "version: one\n", "MSN104"),
        ("version: 1\n", 'version: "1"\n', "MSN106"),
        ("version: 1\n", "version: true\n", "MSN106"),
        ("format: json\n", "", "MSN106"),
        ("format: json\n", "format: json\nformatt: json\n", "MSN106"),
        ("format: json\n", "format: 7\n", "MSN106"),
    ],
)
def test_a_bad_source_fails_validation_with_a_rule_id_and_a_fix(
    project: Path, old: str, new: str, rule: str
):
    edit(project, SOURCE, old, new)

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == rule
    assert diagnostic["file"] == SOURCE
    assert diagnostic["fix"]


def test_the_platform_contract_is_checked_like_any_other_file(project: Path):
    edit(project, PLATFORM, "kind: platform\n", "")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN101"
    assert diagnostic["file"] == PLATFORM


def test_a_platform_contract_with_three_source_layers_fails_with_the_field_named(project: Path):
    edit(project, PLATFORM, "[bronze, silver]", "[bronze, silver, tin]")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"
    assert "naming.layers.sources" in diagnostic["message"]


def test_every_problem_in_a_file_is_reported_at_once(project: Path):
    edit(project, SOURCE, "format: json\n", "extra: 1\n")

    assert [d["rule"] for d in failures(project)] == ["MSN106", "MSN106"]


@pytest.mark.parametrize("content", ["kind: [", "just a string", ""])
def test_a_file_that_is_not_a_yaml_mapping_fails_with_a_rule_id(project: Path, content: str):
    (project / SOURCE).write_text(content)

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN107"
    assert diagnostic["file"] == SOURCE


def test_a_project_with_no_platform_contract_fails_with_a_rule_id(project: Path):
    (project / PLATFORM).unlink()

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN107"
    assert diagnostic["file"] == PLATFORM


@pytest.mark.parametrize("model", ["dim_date", "fct_orders"])
def test_every_starter_model_declares_its_kind_beside_its_sql(project: Path, model: str):
    config = yaml.safe_load((project / f"domains/sales/models/{model}.yaml").read_text())

    assert config == {"kind": "model", "version": 1, "sql": f"{model}.sql"}


def test_sql_with_no_config_beside_it_fails_validation(project: Path):
    (project / MODEL).unlink()

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN108"
    assert diagnostic["file"] == "domains/sales/models/fct_orders.sql"
    assert "kind: model" in diagnostic["fix"]


def test_a_model_pointing_at_a_missing_sql_file_fails_validation(project: Path):
    edit(project, MODEL, "sql: fct_orders.sql", "sql: fct_order.sql")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN109"
    assert diagnostic["file"] == MODEL
    assert "fct_order.sql" in diagnostic["message"]


def test_a_model_may_name_a_sql_file_with_a_different_stem(project: Path):
    models = project / "domains/sales/models"
    (models / "fct_orders.sql").rename(models / "orders_query.sql")
    edit(project, MODEL, "sql: fct_orders.sql", "sql: orders_query.sql")

    compiled = mason(project, "compile")

    assert compiled.exit_code == 0, compiled.output
    assert (project / "build/src/sales/gold/fct_orders.sql").exists()


def test_a_bad_model_file_fails_like_any_other_kind(project: Path):
    edit(project, MODEL, "kind: model\n", "")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN101"
    assert diagnostic["file"] == MODEL
    assert "kind: model" in diagnostic["fix"]


def test_compile_stops_on_invalid_config_with_the_same_diagnostics(project: Path):
    edit(project, SOURCE, "kind: source\n", "")

    result = mason(project, "compile")

    assert result.exit_code == 1
    assert "MSN101" in result.stdout


def test_deploy_stops_on_invalid_config_before_touching_a_workspace(project: Path):
    edit(project, SOURCE, "version: 1\n", "")

    result = mason(project, "deploy", "--env", "dev")

    assert result.exit_code == 1
    assert "MSN103" in result.stdout


def test_init_writes_a_copy_of_every_kinds_schema(project: Path):
    for kind in ("source", "seed", "model", "platform"):
        copied = json.loads((project / f".mason/schemas/{kind}.v1.json").read_text())
        installed = runner.invoke(app, ["schema", kind, "--json"])
        assert copied == json.loads(installed.stdout)["result"]["json_schema"]


@pytest.mark.parametrize("file", [PLATFORM, SOURCE, MODEL, "domains/sales/models/dim_date.yaml"])
def test_every_generated_file_points_editors_at_a_schema_it_passes(project: Path, file: str):
    path = project / file
    first_line = path.read_text().splitlines()[0]
    assert first_line.startswith(MODELINE)

    schema_file = path.parent / first_line.removeprefix(MODELINE)
    Draft202012Validator(json.loads(schema_file.read_text())).validate(
        yaml.safe_load(path.read_text())
    )
