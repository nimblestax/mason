"""Files in a project that Mason would never read fail, rather than being skipped in silence."""

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


def test_a_yml_source_fails_with_a_fix_naming_its_yaml_name(project: Path):
    sources = project / "domains/sales/sources"
    (sources / "orders.yaml").rename(sources / "orders.yml")

    [failure] = failures(project, "MSN120")

    assert failure["name"] == "yml-config-file"
    assert failure["file"] == "domains/sales/sources/orders.yml"
    assert "orders.yaml" in failure["fix"]


@pytest.mark.parametrize("folder", ["sources", "seeds", "models"])
def test_a_yml_file_fails_in_every_domain_folder(project: Path, folder: str):
    (project / "domains/sales" / folder).mkdir(exist_ok=True)
    (project / "domains/sales" / folder / "extra.yml").write_text("kind: source\n")

    [failure] = failures(project, "MSN120")

    assert failure["file"] == f"domains/sales/{folder}/extra.yml"


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
