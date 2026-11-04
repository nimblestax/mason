"""The Platform Contract, described once by a Pydantic model."""

import json
import shutil
from pathlib import Path
from typing import Literal

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from typer.testing import CliRunner

from mason.cli import app
from mason.kinds import platform
from mason.load import config
from mason.load.project import load
from mason.scaffold import PLACEHOLDER_HOST

runner = CliRunner()

PLATFORM = "mason.platform.yaml"


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def edit(project: Path, old: str, new: str) -> None:
    path = project / PLATFORM
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("version: 1\n", 'version: "1"\n', "version"),
        ("version: 1\n", "version: true\n", "version"),
        ("domains:\n", "colour: blue\ndomains:\n", "colour"),
        ("    models: [gold]\n", "    models: gold\n", "naming.layers.models"),
        ('  schema: "{layer}"', "  schema: 7", "naming.schema"),
    ],
)
def test_a_bad_platform_contract_names_the_field_in_an_msn106(
    project: Path, old: str, new: str, field: str
):
    edit(project, old, new)

    diagnostics = failures(project)

    assert {d["rule"] for d in diagnostics} == {"MSN106"}
    assert any(d["message"].startswith(f"{field}: ") for d in diagnostics), diagnostics
    assert all(d["file"] == PLATFORM for d in diagnostics)


def platform_schema() -> dict:
    result = runner.invoke(app, ["schema", "platform", "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["result"]["json_schema"]


def test_the_served_schema_passes_a_valid_contract_and_fails_invalid_ones(project: Path):
    validator = Draft202012Validator(platform_schema())
    contract = yaml.safe_load((project / PLATFORM).read_text())

    assert list(validator.iter_errors(contract)) == []
    for bad in ({"version": "1"}, {"version": True}, {"colour": "blue"}, {"name": 7}):
        assert list(validator.iter_errors({**contract, **bad})), bad


def test_the_served_schema_titles_and_describes_every_field():
    json_schema = platform_schema()

    assert json_schema["title"] == "Mason Platform Contract"
    objects = [json_schema, *json_schema["$defs"].values()]
    for described in objects:
        assert described["title"] and described["description"]
        for name, field in described["properties"].items():
            assert field["description"], name


def test_the_text_schema_lists_every_field_with_its_description():
    result = runner.invoke(app, ["schema", "platform"])

    assert result.exit_code == 0, result.output
    assert "naming (required): The catalog and schema patterns" in result.stdout
    assert "domains (required)" in result.stdout


def test_a_valid_contract_loads_with_its_layers_and_hosts(project: Path):
    loaded = load(project)

    assert loaded.platform.source_layers == ("bronze", "silver")
    assert loaded.platform.model_layers == ("gold",)
    assert loaded.platform.hosts == {"dev": PLACEHOLDER_HOST}


def test_a_repeated_domain_names_the_field(project: Path):
    edit(project, "  - sales\n", "  - sales\n  - sales\n")

    [diagnostic] = failures(project)

    assert diagnostic["message"].startswith("domains: ")
    assert "sales" in diagnostic["message"]


class PlatformV2(BaseModel):
    """A stand-in second version that renames `name` to `project`."""

    model_config = platform.STRICT

    kind: Literal["platform"]
    version: Literal[2]
    project: str


def upgrade_to_v2(old: platform.PlatformV1) -> PlatformV2:
    return PlatformV2(kind="platform", version=2, project=old.name)


def test_a_version_1_contract_is_upgraded_to_the_latest_version(project: Path, monkeypatch):
    monkeypatch.setattr(platform, "VERSIONS", {1: platform.PlatformV1, 2: PlatformV2})
    monkeypatch.setattr(platform, "UPGRADES", {1: upgrade_to_v2})
    written = yaml.safe_load((project / PLATFORM).read_text())

    upgraded = config.load(project, project / PLATFORM, platform.KIND, PlatformV2)

    assert upgraded == PlatformV2(kind="platform", version=2, project=written["name"])


@pytest.mark.parametrize(
    ("new", "field"),
    [
        ('  catalog: "{env}_{team}"', "naming.catalog"),
        ('  catalog: "{env}_{0}"', "naming.catalog"),
        ('  catalog: "{env}_{domain"', "naming.catalog"),
        ('  schema: "{layer}_}"', "naming.schema"),
        ('  schema: "{layer!r}"', "naming.schema"),
    ],
)
def test_a_pattern_with_anything_but_known_placeholders_fails_with_an_msn106(
    project: Path, new: str, field: str
):
    old = '  catalog: "{env}_{domain}"' if "catalog" in new else '  schema: "{layer}"'
    edit(project, old, new)

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"
    assert diagnostic["message"].startswith(f"{field}: ")
    assert "{env}, {domain} and {layer}" in diagnostic["message"]


def test_a_project_with_no_domains_compiles_to_a_package_with_no_pipelines(project: Path):
    edit(project, "domains:\n  - sales\n", "domains: []\n")
    shutil.rmtree(project / "domains")

    result = mason(project, "compile")

    assert result.exit_code == 0, result.output
    bundle = yaml.safe_load((project / "build/databricks.yml").read_text())
    assert bundle["resources"]["pipelines"] == {}
