"""A Source's `path`: one value that may name `{env}`, kept out of generated code."""

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
STARTER_PATH = "path: /Volumes/{env}_sales/bronze/landing/orders\n"


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


def add_environments(project: Path, host: str | None = None) -> None:
    contract = project / "mason.platform.yaml"
    content = yaml.safe_load(contract.read_text())
    host = host or content["environments"]["dev"]["host"]
    content["environments"] = {env: {"host": host} for env in ("dev", "test", "prod")}
    contract.write_text(yaml.safe_dump(content, sort_keys=False))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    add_environments(tmp_path)
    return tmp_path


def declare_path(project: Path, line: str) -> None:
    file = project / SOURCE
    assert STARTER_PATH in file.read_text()
    file.write_text(file.read_text().replace(STARTER_PATH, line))


def package(project: Path) -> tuple[str, dict]:
    result = mason(project, "compile")
    assert result.exit_code == 0, result.output
    code = (project / "build/src/sales/ingest/orders.sql").read_text()
    return code, yaml.safe_load((project / "build/databricks.yml").read_text())


def path_setting_per_target(bundle: dict) -> dict[str, str]:
    return {env: t["variables"]["path_sales__orders"] for env, t in bundle["targets"].items()}


def test_a_path_naming_env_compiles_to_one_file_with_a_setting_for_each_target(project: Path):
    code, bundle = package(project)

    assert "read_files('${path_sales__orders}', format => 'json')" in code
    assert [f.name for f in (project / "build/src/sales/ingest").iterdir()] == ["orders.sql"]
    assert path_setting_per_target(bundle) == {
        "dev": "/Volumes/dev_sales/bronze/landing/orders",
        "test": "/Volumes/test_sales/bronze/landing/orders",
        "prod": "/Volumes/prod_sales/bronze/landing/orders",
    }


def test_a_path_without_env_is_one_shared_location_and_stays_valid(project: Path):
    declare_path(project, "path: /Volumes/shared/landing/orders\n")

    _, bundle = package(project)

    assert set(path_setting_per_target(bundle).values()) == {"/Volumes/shared/landing/orders"}
    assert mason(project, "validate").exit_code == 0


def test_env_can_sit_anywhere_in_a_cloud_path(project: Path):
    declare_path(project, "path: abfss://landing@{env}lake.dfs.core.windows.net/{env}/orders\n")

    _, bundle = package(project)

    assert (
        path_setting_per_target(bundle)["prod"]
        == "abfss://landing@prodlake.dfs.core.windows.net/prod/orders"
    )


def test_only_env_is_replaced_so_a_glob_keeps_its_braces(project: Path):
    declare_path(project, "path: /Volumes/{env}_sales/landing/{2024,2025}/orders\n")

    _, bundle = package(project)

    assert (
        path_setting_per_target(bundle)["test"] == "/Volumes/test_sales/landing/{2024,2025}/orders"
    )


def test_changing_a_path_changes_settings_and_leaves_generated_code_byte_identical(project: Path):
    code_before, settings_before = package(project)

    declare_path(project, "path: /Volumes/{env}_sales/bronze/elsewhere/orders\n")
    code_after, settings_after = package(project)

    assert code_after == code_before
    assert settings_after != settings_before


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_compile_for_an_environment_prints_that_environments_path(project: Path, env: str):
    result = mason(project, "compile", "--env", env)

    assert result.exit_code == 0, result.output
    assert f"read_files('/Volumes/{env}_sales/bronze/landing/orders'" in result.stdout
    assert "${" not in result.stdout
    assert "{env}" not in result.stdout


@pytest.mark.parametrize(
    "line",
    ["path: ''\n", "path: 5\n", "path: {}\n", "path:\n  dev: /a\n  prod: /b\n"],
)
def test_anything_but_one_non_empty_value_fails_against_the_schema(project: Path, line: str):
    declare_path(project, line)

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
    add_environments(tmp_path, stub_workspace)
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
    assert pipeline["configuration"]["path_sales__orders"] == (
        "/Volumes/prod_sales/bronze/landing/orders"
    )
