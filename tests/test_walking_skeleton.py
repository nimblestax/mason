"""The walking skeleton, driven through the real CLI."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason.cli import app
from mason.deploy import deploy
from mason.deploy.databricks import WorkspaceError
from mason.load.project import load

runner = CliRunner()


class FakeWorkspace:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple] = []
        self.fail_on = fail_on

    def deploy_bundle(self, package: Path, target: str) -> None:
        self._record("deploy", package, target)

    def run_job(self, package: Path, target: str, job: str) -> None:
        self._record("run", package, target, job)

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        return []

    def _record(self, *call) -> None:
        self.calls.append(call)
        if call[0] == self.fail_on:
            raise WorkspaceError(f"{call[0]} failed")


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    result = mason(tmp_path, "init", "--ci", "github")
    assert result.exit_code == 0, result.output
    return tmp_path


def test_a_freshly_initialised_project_validates_with_no_workspace(project: Path):
    result = mason(project, "validate", "--json")

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == "mason.validate/1"
    assert envelope["ok"] is True
    assert envelope["diagnostics"] == []


def test_generated_code_uses_placeholders_and_never_real_names(project: Path):
    result = mason(project, "compile")

    assert result.exit_code == 0, result.output
    gold = (project / "build/src/sales/gold/fct_orders.sql").read_text()
    assert "${catalog_sales_gold}.${schema_sales_gold}.fct_orders" in gold
    assert "FROM ${catalog_sales_silver}.${schema_sales_silver}.orders" in gold
    assert "dev_sales" not in gold


def test_compile_for_an_environment_prints_runnable_sql(project: Path):
    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
    assert "CREATE OR REFRESH MATERIALIZED VIEW dev_sales.gold.fct_orders" in result.stdout
    assert "FROM dev_sales.silver.orders" in result.stdout
    assert "${" not in result.stdout


def test_a_source_lands_in_bronze_and_silver(project: Path):
    mason(project, "compile")

    ingest = (project / "build/src/sales/ingest/orders.sql").read_text()
    assert "STREAMING TABLE ${catalog_sales_bronze}.${schema_sales_bronze}.orders" in ingest
    assert "read_files('${path_sales__orders}'" in ingest
    assert "'pipelines.reset.allowed' = 'false'" in ingest
    assert "STREAMING TABLE ${catalog_sales_silver}.${schema_sales_silver}.orders" in ingest
    assert "STREAM(${catalog_sales_bronze}.${schema_sales_bronze}.orders)" in ingest


def test_every_real_name_follows_the_platform_contract_patterns(project: Path):
    contract = project / "mason.platform.yaml"
    contract.write_text(contract.read_text().replace('"{env}_{domain}"', '"{env}_lake_{domain}"'))

    result = mason(project, "compile", "--env", "dev")

    assert "dev_lake_sales.gold.fct_orders" in result.stdout
    assert "dev_sales" not in result.stdout.replace("/Volumes/dev_sales", "")


def test_nothing_in_the_generated_code_refers_to_mason(project: Path):
    mason(project, "compile")

    generated = [f for f in (project / "build/src").rglob("*") if f.is_file()]
    assert generated
    assert all("mason" not in f.read_text().lower() for f in generated)


def test_a_model_reading_an_unknown_logical_name_fails_with_a_rule_id(project: Path):
    model = project / "domains/sales/models/fct_orders.sql"
    model.write_text("SELECT * FROM sales.silver.nonexistent")

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN201"
    assert diagnostic["file"] == "domains/sales/models/fct_orders.sql"
    assert "sales.silver.nonexistent" in diagnostic["message"]
    assert diagnostic["fix"]


def test_compile_writes_a_package_databricks_accepts(tmp_path: Path, stub_workspace: str):
    runner.invoke(app, ["init", "--project", str(tmp_path), "--host", stub_workspace])

    assert mason(tmp_path, "compile").exit_code == 0

    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "DATABRICKS_HOST": stub_workspace,
        "DATABRICKS_TOKEN": "not-a-real-token",
    }
    validated = subprocess.run(
        ["databricks", "bundle", "validate", "--target", "dev", "--output", "json"],
        cwd=tmp_path / "build",
        env=environment,
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0, validated.stderr
    resources = json.loads(validated.stdout)["resources"]
    assert set(resources["pipelines"]) == {"sales_ingest", "sales_gold"}
    assert (
        resources["pipelines"]["sales_gold"]["configuration"]["catalog_sales_gold"] == "dev_sales"
    )
    [job] = resources["jobs"].values()
    tasks = {task["task_key"]: task for task in job["tasks"]}
    assert tasks["sales_gold"]["depends_on"] == [{"task_key": "sales_ingest"}]


def test_deploy_ships_the_package_and_then_refreshes_it(project: Path):
    workspace = FakeWorkspace()

    deploy.deploy(load(project), "dev", workspace)

    assert workspace.calls == [
        ("deploy", project / "build", "dev"),
        ("run", project / "build", "dev", "refresh"),
    ]
    assert (project / "build/databricks.yml").exists()


def test_deploy_refuses_a_project_that_fails_validation(project: Path):
    (project / "domains/sales/models/fct_orders.sql").write_text("SELECT * FROM sales.silver.nope")
    workspace = FakeWorkspace()

    with pytest.raises(deploy.InvalidProject):
        deploy.deploy(load(project), "dev", workspace)

    assert workspace.calls == []


def test_a_failed_deploy_never_refreshes(project: Path):
    workspace = FakeWorkspace(fail_on="deploy")

    with pytest.raises(WorkspaceError):
        deploy.deploy(load(project), "dev", workspace)

    assert [call[0] for call in workspace.calls] == ["deploy"]


def test_github_ci_files_are_thin_calls_to_mason_with_no_secret(project: Path):
    pull_request = (project / ".github/workflows/mason-pull-request.yml").read_text()
    merge = (project / ".github/workflows/mason-merge.yml").read_text()

    assert "mason validate" in pull_request
    assert "mason deploy --env dev" in merge
    assert "id-token: write" in merge
    assert "DATABRICKS_AUTH_TYPE: github-oidc" in merge
    assert "secrets." not in pull_request + merge


def test_generated_code_is_uploaded_even_though_init_gitignores_the_package(project: Path):
    mason(project, "compile")

    assert "build/" in (project / ".gitignore").read_text()
    package = yaml.safe_load((project / "build/databricks.yml").read_text())
    assert package["sync"]["include"] == ["src/**"]


def test_a_deleted_model_leaves_the_package(project: Path):
    mason(project, "compile")
    (project / "domains/sales/models/fct_orders.sql").unlink()
    (project / "domains/sales/models/fct_orders.yaml").unlink()

    mason(project, "compile")

    assert not (project / "build/src/sales/gold/fct_orders.sql").exists()
