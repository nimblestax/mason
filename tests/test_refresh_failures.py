"""A refresh that fails says why, from the pipeline's own error, and fails fast."""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason import cli
from mason.deploy.databricks import WorkspaceError, failed_update_errors

runner = CliRunner()

EXPECTATION_FIRED = (
    "[EXPECTATION_VIOLATION.VERBOSITY_ALL] Flow 'orders' failed to meet the expectation."
    " Violated expectations: 'amount_not_negative'"
)
COLUMN_MISSING = (
    "[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column, variable, or function parameter with name"
    " `region` cannot be resolved. Did you mean one of the following? [`amount`]."
)


class FailingRefresh:
    """A workspace whose refresh fails, with these errors in the pipelines' event logs."""

    def __init__(self, errors: list[str], unreadable: bool = False):
        self.errors = errors
        self.unreadable = unreadable
        self.since: datetime | None = None

    def deploy_bundle(self, package: Path, target: str) -> None:
        pass

    def run_job(self, package: Path, target: str, job: str) -> None:
        raise WorkspaceError("databricks bundle run failed. Its last lines:\nTERMINATED FAILED")

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        self.since = since
        if self.unreadable:
            raise WorkspaceError("databricks pipelines list-pipeline-events failed.")
        return self.errors


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(cli.app, ["init", "--project", str(tmp_path)]).exit_code == 0
    return tmp_path


def deploy(project: Path, workspace: FailingRefresh, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(cli, "DatabricksCli", lambda: workspace)
    result = runner.invoke(cli.app, ["deploy", "--env", "dev", "--json", "--project", str(project)])
    assert result.exit_code == 2, result.output
    return json.loads(result.stdout)


def test_a_fail_expectation_that_fired_is_reported_with_the_pipelines_message(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    envelope = deploy(project, FailingRefresh([EXPECTATION_FIRED]), monkeypatch)

    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN907"
    assert diagnostic["name"] == "expectation-failed"
    assert diagnostic["message"] == EXPECTATION_FIRED
    assert "`quarantine` or `warn`" in diagnostic["fix"]


def test_a_rule_on_a_column_bronze_does_not_have_yet_is_reported(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    envelope = deploy(project, FailingRefresh([COLUMN_MISSING]), monkeypatch)

    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN906"
    assert diagnostic["message"] == COLUMN_MISSING
    assert "without the rule" in diagnostic["fix"]


def test_any_other_pipeline_failure_is_reported_with_its_message(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    envelope = deploy(project, FailingRefresh(["[DIVIDE_BY_ZERO] Division by zero."]), monkeypatch)

    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN908"
    assert diagnostic["message"] == "[DIVIDE_BY_ZERO] Division by zero."


def test_each_failed_pipeline_gets_its_own_diagnostic(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    envelope = deploy(project, FailingRefresh([COLUMN_MISSING, EXPECTATION_FIRED]), monkeypatch)

    assert [found["rule"] for found in envelope["diagnostics"]] == ["MSN906", "MSN907"]


def test_errors_are_read_from_updates_since_the_refresh_started(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    workspace = FailingRefresh([EXPECTATION_FIRED])
    before = datetime.now().astimezone()

    deploy(project, workspace, monkeypatch)

    assert workspace.since is not None
    assert workspace.since >= before


@pytest.mark.parametrize("workspace", [FailingRefresh([]), FailingRefresh([], unreadable=True)])
def test_with_no_pipeline_error_to_read_the_cli_output_is_reported(
    project: Path, monkeypatch: pytest.MonkeyPatch, workspace: FailingRefresh
):
    envelope = deploy(project, workspace, monkeypatch)

    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN904"
    assert "TERMINATED FAILED" in diagnostic["message"]


def test_a_pipeline_retries_a_failed_update_once_in_every_environment(project: Path):
    assert runner.invoke(cli.app, ["compile", "--project", str(project)]).exit_code == 0

    bundle = yaml.safe_load((project / "build/databricks.yaml").read_text())

    for pipeline in bundle["resources"]["pipelines"].values():
        assert pipeline["configuration"]["pipelines.numUpdateRetryAttempts"] == "1"
    for target in bundle["targets"].values():
        assert "resources" not in target


# The real boundary, driven through the installed command with a fake `databricks` on the PATH.


def event(update: str, message: str, flow: str | None = None) -> dict:
    """One ERROR event, in the shape `databricks pipelines list-pipeline-events -o json` prints."""
    origin = {"pipeline_id": "p-ingest", "update_id": update}
    if flow:
        origin["flow_name"] = flow
    return {
        "id": f"{update}-{flow}",
        "event_type": "flow_progress" if flow else "update_progress",
        "level": "ERROR",
        "message": f"Flow '{flow}' has FAILED." if flow else message,
        "origin": origin,
        "error": {"exceptions": [{"class_name": "Exception", "message": message}], "fatal": True},
    }


# Newest first, as the event log returns them: the retry, then the first attempt.
EVENTS = [
    event("u2", "Update u2 is FAILED since flow orders failed an expectation check."),
    event("u2", EXPECTATION_FIRED + "\n\tat com.databricks.Something", flow="orders"),
    event("u1", "Update u1 is FAILED since flow orders failed an expectation check."),
    event("u1", EXPECTATION_FIRED + "\n\tat com.databricks.Something", flow="orders"),
]

SUMMARY = {
    "bundle": {"name": "mason_probe"},
    "resources": {
        "pipelines": {
            "sales_ingest": {"id": "p-ingest", "name": "mason_probe_sales_ingest"},
            "sales_gold": {"id": "p-gold", "name": "mason_probe_sales_gold"},
        }
    },
}


def fake_databricks(folder: Path, events: dict[str, list[dict]]) -> Path:
    """A Databricks CLI whose refresh fails, with these events in each pipeline's log."""
    bin_folder = folder / "bin"
    bin_folder.mkdir()
    (folder / "summary.json").write_text(json.dumps(SUMMARY))
    for pipeline, logged in events.items():
        (folder / f"{pipeline}.json").write_text(json.dumps(logged))
    script = bin_folder / "databricks"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {folder}/calls\n'
        'case "$1 $2" in\n'
        '  "bundle run") echo \'"mason_probe_refresh" RUNNING\'; echo \'"mason_probe_refresh"'
        " TERMINATED FAILED'; echo 'Error: run failed' >&2; exit 1 ;;\n"
        f'  "bundle summary") /bin/cat {folder}/summary.json ;;\n'
        f'  "pipelines list-pipeline-events") /bin/cat {folder}/$3.json ;;\n'
        "esac\n"
    )
    script.chmod(0o755)
    return bin_folder


def run_mason(project: Path, path: Path) -> subprocess.CompletedProcess:
    executable = Path(sys.executable).with_name("mason")
    arguments = ["deploy", "--env", "dev", "--json", "--project", str(project)]
    return subprocess.run(
        [executable, *arguments], capture_output=True, text=True, env={"PATH": str(path)}
    )


def test_the_failed_updates_error_is_read_from_the_event_log(project: Path, tmp_path_factory):
    folder = tmp_path_factory.mktemp("cli")
    path = fake_databricks(folder, {"p-ingest": EVENTS, "p-gold": []})

    result = run_mason(project, path)

    assert result.returncode == 2, result.stderr
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN907"
    assert diagnostic["message"] == EXPECTATION_FIRED
    assert "TERMINATED FAILED" in result.stderr
    calls = (folder / "calls").read_text().splitlines()
    assert "bundle summary --target dev -o json" in calls
    [listing] = [call for call in calls if "list-pipeline-events p-ingest" in call]
    assert "--target dev -o json --filter level='ERROR' AND timestamp >= '" in listing


def test_the_cli_output_is_reported_when_no_pipeline_logged_an_error(
    project: Path, tmp_path_factory
):
    path = fake_databricks(tmp_path_factory.mktemp("cli"), {"p-ingest": [], "p-gold": []})

    result = run_mason(project, path)

    assert result.returncode == 2, result.stderr
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN904"
    assert "TERMINATED FAILED" in diagnostic["message"]
    assert "Error: run failed" in diagnostic["message"]
    assert "TERMINATED FAILED" in result.stderr


def test_only_the_newest_updates_flow_errors_are_kept():
    assert failed_update_errors(EVENTS) == [EXPECTATION_FIRED]


def test_an_older_updates_error_is_not_kept():
    events = [event("u2", EXPECTATION_FIRED, flow="orders"), event("u1", COLUMN_MISSING, "orders")]

    assert failed_update_errors(events) == [EXPECTATION_FIRED]


def test_an_update_with_no_flow_error_keeps_its_own_error():
    events = [event("u1", "Update u1 has failed. Out of quota.\nDetails follow.")]

    assert failed_update_errors(events) == ["Update u1 has failed. Out of quota."]


def test_each_failed_flow_in_the_update_is_kept_once():
    events = [
        event("u1", EXPECTATION_FIRED, flow="orders"),
        event("u1", COLUMN_MISSING, flow="customers"),
        event("u1", EXPECTATION_FIRED, flow="orders"),
    ]

    assert failed_update_errors(events) == [EXPECTATION_FIRED, COLUMN_MISSING]


def test_no_events_means_no_errors():
    assert failed_update_errors([]) == []
