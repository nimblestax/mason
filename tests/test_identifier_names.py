"""Names Mason writes into SQL unquoted, and values it writes as SQL string literals."""

import json
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()

SOURCES = "domains/sales/sources"
STARTER_PATH = "path: /Volumes/{env}_sales/bronze/landing/orders\n"


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def copy(project: Path, old: str, new: str) -> None:
    (project / new).write_text((project / old).read_text())


@pytest.mark.parametrize(
    ("old", "new", "suggested"),
    [
        (f"{SOURCES}/orders.yaml", f"{SOURCES}/web-events.yaml", "web_events.yaml"),
        (f"{SOURCES}/orders.yaml", f"{SOURCES}/2024 orders.yaml", "_2024_orders.yaml"),
        (
            "domains/sales/models/dim_date.yaml",
            "domains/sales/models/dim.dates.yaml",
            "dim_dates.yaml",
        ),
    ],
)
def test_a_config_file_whose_name_isnt_an_identifier_fails_with_msn117(
    project: Path, old: str, new: str, suggested: str
):
    copy(project, old, new)

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN117"
    assert diagnostic["name"] == "invalid-name"
    assert diagnostic["file"] == new
    assert suggested in diagnostic["fix"]


def test_a_seed_whose_name_isnt_an_identifier_fails_with_msn117(project: Path):
    seeds = project / "domains/sales/seeds"
    seeds.mkdir()
    (seeds / "vat-rates.yaml").write_text(
        "kind: seed\nversion: 1\nfile: rates.csv\ncolumns:\n  code: STRING\n"
    )
    (seeds / "rates.csv").write_text("code\nAU\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN117"
    assert diagnostic["file"] == "domains/sales/seeds/vat-rates.yaml"


@pytest.mark.parametrize("domain", ["sales-eu", "2024", "sales eu"])
def test_a_domain_that_isnt_an_identifier_fails_with_msn106(project: Path, domain: str):
    contract = project / "mason.platform.yaml"
    contract.write_text(contract.read_text().replace("  - sales\n", f'  - sales\n  - "{domain}"\n'))
    (project / "domains" / domain).mkdir()

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"
    assert diagnostic["file"] == "mason.platform.yaml"
    assert diagnostic["message"].startswith("domains.1: ")


@pytest.mark.parametrize(
    "path",
    [
        "/Volumes/dev_sales/landing/o'rders",
        "/Volumes/dev_sales/landing/back\\slash\\",
        "/Volumes/dev_sales/landing/${price}",
        "/Volumes/dev_sales/landing/o'r\\d${x}${",
    ],
)
def test_a_path_compiles_to_a_read_files_literal_of_the_same_value(project: Path, path: str):
    source = project / SOURCES / "orders.yaml"
    source.write_text(source.read_text().replace(STARTER_PATH, f"path: {json.dumps(path)}\n"))

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
    [read_files] = [line for line in result.stdout.splitlines() if "read_files(" in line]
    # Lakeflow would substitute a `${` left in the literal as a placeholder.
    assert "${" not in read_files
    literal = sqlglot.parse_one(f"SELECT {_first_argument(read_files)}", dialect="databricks")
    assert _decoded(literal.find(exp.Literal)) == path


def _first_argument(line: str) -> str:
    return line.split("read_files(", 1)[1].rsplit(", format =>", 1)[0]


def _decoded(literal: exp.Literal | None) -> str:
    # Databricks reads `$` in a string literal as `$`; sqlglot leaves it as written.
    assert literal is not None and literal.is_string
    return literal.this.replace("\\u0024", "$")
