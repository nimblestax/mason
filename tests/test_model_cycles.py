"""A Gold Model can't read itself, or read Models that read it back."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app

MODELS = "domains/sales/models"

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def write_model(project: Path, name: str, query: str) -> None:
    (project / MODELS / f"{name}.yaml").write_text(f"kind: model\nversion: 1\nsql: {name}.sql\n")
    (project / MODELS / f"{name}.sql").write_text(query)


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def test_two_gold_models_that_read_each_other_fail_once_naming_both(project: Path):
    write_model(project, "a", "SELECT * FROM sales.gold.b")
    write_model(project, "b", "SELECT * FROM sales.gold.a")

    [failure] = failures(project)

    assert failure["rule"] == "MSN208"
    assert failure["name"] == "model-cycle"
    assert failure["file"] == f"{MODELS}/a.sql"
    assert "sales.gold.a → sales.gold.b → sales.gold.a" in failure["message"]
    assert failure["fix"]


def test_a_gold_model_that_reads_itself_fails(project: Path):
    write_model(project, "fct_orders", "SELECT * FROM sales.gold.fct_orders")

    [failure] = failures(project)

    assert failure["rule"] == "MSN208"
    assert failure["file"] == f"{MODELS}/fct_orders.sql"
    assert "sales.gold.fct_orders → sales.gold.fct_orders" in failure["message"]


def test_a_longer_cycle_is_reported_once_naming_every_model_in_order(project: Path):
    write_model(project, "c", "SELECT * FROM sales.gold.a")
    write_model(project, "b", "SELECT * FROM sales.gold.c JOIN sales.gold.dim_date USING (d)")
    write_model(project, "a", "SELECT * FROM sales.gold.b")

    [failure] = failures(project)

    assert failure["file"] == f"{MODELS}/a.sql"
    assert "sales.gold.a → sales.gold.b → sales.gold.c → sales.gold.a" in failure["message"]


def test_each_separate_cycle_is_reported(project: Path):
    write_model(project, "a", "SELECT * FROM sales.gold.b")
    write_model(project, "b", "SELECT * FROM sales.gold.a")
    write_model(project, "x", "SELECT * FROM sales.gold.x")

    assert [failure["file"] for failure in failures(project)] == [
        f"{MODELS}/a.sql",
        f"{MODELS}/x.sql",
    ]


def test_models_that_read_in_a_line_pass(project: Path):
    write_model(project, "a", "SELECT * FROM sales.gold.fct_orders")
    write_model(project, "b", "SELECT * FROM sales.gold.a JOIN sales.gold.fct_orders USING (id)")

    result = mason(project, "validate", "--json")

    assert result.exit_code == 0, result.output
