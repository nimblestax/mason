"""Config files are read whether they end in `.yaml` or `.yml`, and unread folders fail."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app

PLATFORM = "mason.platform.yaml"

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def failures(project: Path, rule: str) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return [d for d in json.loads(result.stdout)["diagnostics"] if d["rule"] == rule]


def list_domains(project: Path, *domains: str) -> None:
    platform = project / PLATFORM
    listed = "".join(f"  - {domain}\n" for domain in domains)
    platform.write_text(platform.read_text().replace("  - sales\n", listed))


def compiled(project: Path) -> str:
    result = mason(project, "compile", "--env", "dev")
    assert result.exit_code == 0, result.output
    return result.stdout


def test_a_yml_source_is_read_like_a_yaml_one(project: Path):
    sources = project / "domains/sales/sources"
    (sources / "orders.yaml").rename(sources / "orders.yml")

    assert "STREAMING TABLE dev_sales.bronze.orders" in compiled(project)


def test_a_yml_model_is_read_and_its_sql_has_a_config_file(project: Path):
    models = project / "domains/sales/models"
    (models / "fct_orders.yaml").rename(models / "fct_orders.yml")

    assert "MATERIALIZED VIEW dev_sales.gold.fct_orders" in compiled(project)


@pytest.mark.parametrize("folder", ["sources", "seeds", "models"])
def test_a_name_with_both_a_yaml_and_a_yml_file_fails_once(project: Path, folder: str):
    (project / "domains/sales" / folder).mkdir(exist_ok=True)
    for suffix in (".yaml", ".yml"):
        (project / "domains/sales" / folder / f"extra{suffix}").write_text("kind: source\n")

    [failure] = failures(project, "MSN120")

    assert failure["name"] == "duplicate-config-file"
    assert failure["file"] == f"domains/sales/{folder}/extra.yml"
    assert "extra.yaml" in failure["message"]


def test_a_domain_folder_the_platform_contract_does_not_list_fails(project: Path):
    (project / "domains/hr/sources").mkdir(parents=True)

    [failure] = failures(project, "MSN121")

    assert failure["name"] == "unlisted-domain-folder"
    assert failure["file"] == "domains/hr"
    assert "hr" in failure["fix"]
    assert PLATFORM in failure["fix"]


def test_a_domain_listed_in_another_case_does_not_name_its_folder(project: Path):
    list_domains(project, "Sales")

    [failure] = failures(project, "MSN121")

    assert failure["file"] == "domains/sales"
    assert "Sales" in failure["message"]
    assert "sales" in failure["fix"]


def test_every_listed_domain_folder_and_yaml_file_passes(project: Path):
    (project / "domains/hr/sources").mkdir(parents=True)
    list_domains(project, "sales", "hr")
    (project / "domains/.DS_Store").write_text("")

    result = mason(project, "validate", "--json")

    assert result.exit_code == 0, result.output
