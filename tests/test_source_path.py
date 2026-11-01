"""A Source's `path`: one value, or one per Environment, kept out of generated code."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()

SOURCE = "domains/sales/sources/orders.yaml"
SINGLE_PATH = "path: /Volumes/dev_sales/bronze/landing/orders\n"
PER_ENVIRONMENT_PATH = """path:
  dev: /Volumes/dev_sales/bronze/landing/orders
  test: /Volumes/test_sales/bronze/landing/orders
  prod: abfss://landing@prod.dfs.core.windows.net/orders
"""


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    contract = tmp_path / "mason.platform.yaml"
    content = yaml.safe_load(contract.read_text())
    host = content["environments"]["dev"]["host"]
    content["environments"] = {env: {"host": host} for env in ("dev", "test", "prod")}
    contract.write_text(yaml.safe_dump(content, sort_keys=False))
    return tmp_path


def declare_path(project: Path, block: str) -> None:
    file = project / SOURCE
    file.write_text(file.read_text().replace(SINGLE_PATH, block))


def package(project: Path) -> tuple[str, dict]:
    result = mason(project, "compile")
    assert result.exit_code == 0, result.output
    code = (project / "build/src/sales/ingest/orders.sql").read_text()
    return code, yaml.safe_load((project / "build/databricks.yml").read_text())


def test_a_per_environment_path_compiles_to_one_file_with_a_setting_for_each_target(
    project: Path,
):
    declare_path(project, PER_ENVIRONMENT_PATH)

    code, bundle = package(project)

    assert "read_files('${path_sales__orders}', format => 'json')" in code
    assert [f.name for f in (project / "build/src/sales/ingest").iterdir()] == ["orders.sql"]
    assert {env: t["variables"]["path_sales__orders"] for env, t in bundle["targets"].items()} == {
        "dev": "/Volumes/dev_sales/bronze/landing/orders",
        "test": "/Volumes/test_sales/bronze/landing/orders",
        "prod": "abfss://landing@prod.dfs.core.windows.net/orders",
    }


def test_a_path_missing_for_an_environment_fails_validation_with_a_rule_id(project: Path):
    declare_path(project, "path:\n  dev: /Volumes/dev_sales/bronze/landing/orders\n")

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1, result.output
    missing = json.loads(result.stdout)["diagnostics"]
    assert [d["rule"] for d in missing] == ["MSN112", "MSN112"]
    assert {d["file"] for d in missing} == {SOURCE}
    assert "`test`" in missing[0]["message"] + missing[1]["message"]
    assert "`prod`" in missing[0]["message"] + missing[1]["message"]
    assert "path" in missing[0]["fix"]


def test_a_single_path_goes_to_every_target_from_the_same_generated_code(project: Path):
    code, bundle = package(project)

    assert "read_files('${path_sales__orders}', format => 'json')" in code
    assert {t["variables"]["path_sales__orders"] for t in bundle["targets"].values()} == {
        "/Volumes/dev_sales/bronze/landing/orders"
    }
    assert mason(project, "validate").exit_code == 0


def test_changing_a_path_changes_settings_and_leaves_generated_code_byte_identical(project: Path):
    declare_path(project, PER_ENVIRONMENT_PATH)
    code_before, settings_before = package(project)

    file = project / SOURCE
    file.write_text(file.read_text().replace("prod.dfs", "elsewhere.dfs"))
    code_after, settings_after = package(project)

    assert code_after == code_before
    assert settings_after != settings_before


@pytest.mark.parametrize(
    ("env", "real_path"),
    [
        ("dev", "/Volumes/dev_sales/bronze/landing/orders"),
        ("prod", "abfss://landing@prod.dfs.core.windows.net/orders"),
    ],
)
def test_compile_for_an_environment_prints_that_environments_path(
    project: Path, env: str, real_path: str
):
    declare_path(project, PER_ENVIRONMENT_PATH)

    result = mason(project, "compile", "--env", env)

    assert result.exit_code == 0, result.output
    assert f"read_files('{real_path}', format => 'json')" in result.stdout
    assert "${" not in result.stdout


def test_compile_and_deploy_stop_on_a_missing_path(project: Path):
    declare_path(project, "path:\n  dev: /Volumes/dev_sales/bronze/landing/orders\n")

    for command in (("compile",), ("compile", "--env", "dev"), ("deploy", "--env", "dev")):
        result = mason(project, *command)
        assert result.exit_code == 1, result.output
        assert "MSN112" in result.stdout


@pytest.mark.parametrize(
    "block",
    [
        "path: ''\n",
        "path: 5\n",
        "path: {}\n",
        "path:\n  dev: ''\n  test: /a\n  prod: /b\n",
        "path:\n  dev: 5\n  test: /a\n  prod: /b\n",
        "path:\n  dev: [/a]\n  test: /a\n  prod: /b\n",
    ],
)
def test_a_malformed_path_fails_against_the_schema(project: Path, block: str):
    declare_path(project, block)

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1, result.output
    assert [d["rule"] for d in json.loads(result.stdout)["diagnostics"]] == ["MSN106"]


def test_two_sources_whose_names_join_alike_keep_separate_settings(project: Path):
    contract = project / "mason.platform.yaml"
    contract.write_text(contract.read_text().replace("- sales\n", "- sales\n- sales_eu\n"))
    (project / "domains/sales_eu/sources").mkdir(parents=True)
    (project / "domains/sales_eu/sources/orders.yaml").write_text(
        "kind: source\nversion: 1\npath: /one\nformat: json\n"
    )
    (project / "domains/sales/sources/eu_orders.yaml").write_text(
        "kind: source\nversion: 1\npath: /two\nformat: json\n"
    )

    _, bundle = package(project)

    settings = bundle["targets"]["prod"]["variables"]
    assert settings["path_sales_eu__orders"] == "/one"
    assert settings["path_sales__eu_orders"] == "/two"


def test_every_target_passes_its_own_path_to_the_pipeline(tmp_path: Path, stub_workspace: str):
    result = runner.invoke(app, ["init", "--project", str(tmp_path), "--host", stub_workspace])
    assert result.exit_code == 0, result.output
    contract = tmp_path / "mason.platform.yaml"
    content = yaml.safe_load(contract.read_text())
    content["environments"]["prod"] = {"host": stub_workspace}
    contract.write_text(yaml.safe_dump(content, sort_keys=False))
    declare_path(
        tmp_path,
        "path:\n  dev: /Volumes/dev_sales/bronze/landing/orders\n  prod: /Volumes/prod/orders\n",
    )
    assert mason(tmp_path, "compile").exit_code == 0

    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "DATABRICKS_HOST": stub_workspace,
        "DATABRICKS_TOKEN": "not-a-real-token",
    }
    validated = subprocess.run(
        ["databricks", "bundle", "validate", "--target", "prod", "--output", "json"],
        cwd=tmp_path / "build",
        env=environment,
        capture_output=True,
        text=True,
    )

    assert validated.returncode == 0, validated.stderr
    pipeline = json.loads(validated.stdout)["resources"]["pipelines"]["sales_ingest"]
    assert pipeline["configuration"]["path_sales__orders"] == "/Volumes/prod/orders"
