"""Source, Seed and Gold Model, each described once by a Pydantic model."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()

SOURCE = "domains/sales/sources/orders.yaml"
SEED = "domains/sales/seeds/countries.yaml"
MODEL = "domains/sales/models/fct_orders.yaml"
SEED_CONFIG = """kind: seed
version: 1
file: countries.csv
columns:
  code: STRING
"""


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    seeds = tmp_path / "domains/sales/seeds"
    seeds.mkdir()
    (seeds / "countries.yaml").write_text(SEED_CONFIG)
    (seeds / "countries.csv").write_text("code\nAU\n")
    return tmp_path


def edit(project: Path, file: str, old: str, new: str) -> None:
    path = project / file
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


@pytest.mark.parametrize(
    ("file", "old", "new", "field"),
    [
        (SOURCE, "version: 1\n", 'version: "1"\n', "version"),
        (SOURCE, "version: 1\n", "version: true\n", "version"),
        (SOURCE, "format: json\n", "format: json\ncolour: blue\n", "colour"),
        (SOURCE, "format: json\n", "format: yaml\n", "format"),
        (SOURCE, "format: json\n", "format: json\nsilver:\n  scd: true\n", "silver.scd"),
        (SOURCE, "format: json\n", "format: json\nsilver:\n  keys: []\n", "silver.keys"),
        (SOURCE, "format: json\n", "format: json\nsilver:\n  keys: [a, a]\n", "silver.keys"),
        (SEED, "version: 1\n", 'version: "1"\n', "version"),
        (SEED, "version: 1\n", "version: true\n", "version"),
        (SEED, "  code: STRING\n", "  code: 7\n", "columns.code"),
        (SEED, "columns:\n  code: STRING\n", "columns: {}\n", "columns"),
        (SEED, "file: countries.csv", "file: data/countries.csv", "file"),
        (MODEL, "version: 1\n", 'version: "1"\n', "version"),
        (MODEL, "version: 1\n", "version: true\n", "version"),
        (MODEL, "sql: fct_orders.sql", "sql: 7", "sql"),
        (MODEL, "sql: fct_orders.sql", "sql: fct_orders.txt", "sql"),
    ],
)
def test_a_bad_field_names_the_field_in_an_msn106(
    project: Path, file: str, old: str, new: str, field: str
):
    edit(project, file, old, new)

    diagnostics = failures(project)

    assert {d["rule"] for d in diagnostics} == {"MSN106"}, diagnostics
    assert any(d["message"].startswith(f"{field}: ") for d in diagnostics), diagnostics
    assert all(d["file"] == file for d in diagnostics)


def test_a_seed_column_name_that_is_not_an_identifier_is_named(project: Path):
    edit(project, SEED, "  code: STRING\n", "  code: STRING\n  vat rate: STRING\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"
    assert diagnostic["message"].startswith("columns.vat rate")


def served_schema(kind: str) -> dict:
    result = runner.invoke(app, ["schema", kind, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["result"]["json_schema"]


@pytest.mark.parametrize(
    ("kind", "file", "bad_values"),
    [
        (
            "source",
            SOURCE,
            [
                {"version": "1"},
                {"version": True},
                {"colour": "blue"},
                {"format": "yaml"},
                {"silver": {"scd": 3}},
                {"silver": {"keys": ["a", "a"]}},
            ],
        ),
        (
            "seed",
            SEED,
            [{"version": True}, {"columns": {}}, {"columns": {"vat rate": "STRING"}}],
        ),
        ("model", MODEL, [{"version": "1"}, {"sql": "a/b.sql"}, {"query": "x"}]),
    ],
)
def test_the_served_schema_passes_a_valid_file_and_fails_invalid_ones(
    project: Path, kind: str, file: str, bad_values: list[dict]
):
    validator = Draft202012Validator(served_schema(kind))
    content = yaml.safe_load((project / file).read_text())

    assert list(validator.iter_errors(content)) == []
    for bad in bad_values:
        assert list(validator.iter_errors({**content, **bad})), bad


@pytest.mark.parametrize(
    ("kind", "title"),
    [("source", "Mason Source"), ("seed", "Mason Seed"), ("model", "Mason Gold Model")],
)
def test_the_served_schema_titles_and_describes_every_field(kind: str, title: str):
    json_schema = served_schema(kind)

    assert json_schema["title"] == title
    objects = [json_schema, *json_schema.get("$defs", {}).values()]
    for described in objects:
        assert described["title"] and described["description"]
        for name, field in described["properties"].items():
            assert field["description"], name


@pytest.mark.parametrize("kind", ["source", "seed", "model"])
def test_the_folder_a_file_lives_in_stays_out_of_the_schema(kind: str):
    properties = served_schema(kind)["properties"]

    assert not {"domain", "name"} & set(properties)
