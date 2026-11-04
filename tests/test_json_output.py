"""The contract machines rely on: one envelope, stable rule IDs and three exit codes."""

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from mason.cli import app
from mason.diagnostics import DOCS, RULES, error

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert mason(tmp_path, "init").exit_code == 0
    return tmp_path


def test_validate_prints_an_envelope_with_the_rule_id_and_exits_1(project: Path):
    (project / "domains/sales/models/fct_orders.sql").write_text("SELECT * FROM sales.silver.nope")

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert list(envelope) == ["schema", "mason_version", "ok", "result", "diagnostics"]
    assert envelope["schema"] == "mason.validate/1"
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert list(diagnostic) == [
        "rule",
        "name",
        "severity",
        "file",
        "line",
        "message",
        "fix",
        "docs",
    ]
    assert diagnostic["rule"] == "MSN201"
    assert diagnostic["file"] == "domains/sales/models/fct_orders.sql"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["init"], {"project": "."}),
        (["validate"], {}),
        (["compile"], {"package": "build"}),
    ],
)
def test_a_command_reports_its_result_in_the_envelope(
    project: Path, monkeypatch, command: list[str], expected: dict
):
    monkeypatch.chdir(project)

    result = runner.invoke(app, [*command, "--json"])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == f"mason.{command[0]}/1"
    assert envelope["ok"] is True
    assert envelope["result"] == expected
    assert envelope["diagnostics"] == []


def test_compile_for_an_environment_returns_the_sql_in_the_envelope(project: Path):
    result = mason(project, "compile", "--env", "dev", "--json")

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["result"]["env"] == "dev"
    assert "dev_sales.gold.fct_orders" in envelope["result"]["sql"]


def test_every_registered_command_has_the_json_option():
    """A new command that doesn't register through the shared wrapper fails here."""
    group: Any = get_command(app)
    commands = group.commands
    assert {"init", "validate", "schema", "compile", "deploy"} <= set(commands)
    for name, registered in commands.items():
        options = [option for parameter in registered.params for option in parameter.opts]
        assert "--json" in options, f"`mason {name}` has no --json"


def run_mason(*args: str, path: Path) -> subprocess.CompletedProcess:
    """The installed command in its own process, so stdout and stderr are the real ones."""
    executable = Path(sys.executable).with_name("mason")
    return subprocess.run(
        [executable, *args], capture_output=True, text=True, env={"PATH": str(path)}
    )


def fake_databricks(folder: Path, exit_code: int = 0) -> Path:
    """A Databricks CLI that logs to stdout, as the real one does for bundle runs."""
    folder.mkdir()
    script = folder / "databricks"
    script.write_text(f"#!/bin/sh\necho 'Uploading bundle files'\nexit {exit_code}\n")
    script.chmod(0o755)
    return folder


def test_stdout_is_pure_json_while_the_databricks_cli_logs(project: Path, tmp_path_factory):
    path = fake_databricks(tmp_path_factory.mktemp("cli") / "bin")

    result = run_mason("deploy", "--env", "dev", "--json", "--project", str(project), path=path)

    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == "mason.deploy/1"
    assert envelope["result"] == {"env": "dev"}
    assert "Uploading bundle files" in result.stderr


def test_a_failing_databricks_command_is_an_environment_error(project: Path, tmp_path_factory):
    path = fake_databricks(tmp_path_factory.mktemp("cli") / "bin", exit_code=3)

    result = run_mason("deploy", "--env", "dev", "--json", "--project", str(project), path=path)

    assert result.returncode == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN904"


def test_a_missing_databricks_cli_is_an_environment_error(project: Path, tmp_path_factory):
    path = tmp_path_factory.mktemp("empty")

    result = run_mason("deploy", "--env", "dev", "--json", "--project", str(project), path=path)

    assert result.returncode == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN903"
    assert "Install" in diagnostic["fix"]


@pytest.mark.parametrize(
    ("arguments", "schema"),
    [
        (["deploy", "--json"], "mason.deploy/1"),
        (["validate", "--json", "--nope"], "mason.validate/1"),
        (["init", "--ci", "gitlab", "--json"], "mason.init/1"),
        (["nope", "--json"], "mason.usage/1"),
    ],
)
def test_a_usage_error_is_an_envelope_that_exits_2(arguments: list[str], schema: str):
    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == schema
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN901"
    assert diagnostic["message"]
    assert "--help" in diagnostic["fix"]


def test_a_usage_error_without_json_stays_text_for_a_person():
    result = runner.invoke(app, ["deploy"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Missing option" in result.stderr


@pytest.mark.parametrize("command", ["compile", "deploy"])
def test_an_unknown_environment_is_a_usage_error_naming_the_environments(
    project: Path, command: str
):
    result = mason(project, command, "--env", "staging", "--json")

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN902"
    assert "dev" in diagnostic["fix"]


@pytest.mark.parametrize("as_json", [True, False])
def test_a_crash_keeps_the_exit_code_contract(tmp_path: Path, as_json: bool):
    in_the_way = tmp_path / "a-file"
    in_the_way.write_text("not a folder")
    flags = ["--json"] if as_json else []

    result = mason(in_the_way, "init", *flags)

    assert result.exit_code == 2
    assert "MSN905" in result.stdout
    assert "Traceback" in result.stderr
    assert "Traceback" not in result.stdout
    if as_json:
        assert json.loads(result.stdout)["schema"] == "mason.init/1"


def test_a_project_problem_without_json_stays_text_for_a_person(project: Path):
    (project / "domains/sales/models/fct_orders.sql").write_text("SELECT * FROM sales.silver.nope")

    result = mason(project, "validate")

    assert result.exit_code == 1
    assert "MSN201 domains/sales/models/fct_orders.sql:" in result.stdout
    assert "Fix: " in result.stdout


# Copied by hand on purpose. Editing a line here means a rule ID changed meaning, was removed or
# was reused, which breaks every agent and script that relies on it. Only ever add lines.
REGISTERED_RULES = {
    "MSN101": "missing-kind",
    "MSN102": "unknown-kind",
    "MSN103": "missing-version",
    "MSN104": "unknown-version",
    "MSN105": "wrong-kind",
    "MSN106": "invalid-field",
    "MSN107": "unreadable-config",
    "MSN108": "sql-without-config",
    "MSN109": "missing-sql-file",
    "MSN110": "keys-without-sequence-by",
    "MSN111": "upsert-field-without-keys",
    "MSN112": "missing-seed-file",
    "MSN113": "seed-header-mismatch",
    "MSN114": "seed-row-mismatch",
    "MSN115": "unsupported-seed-type",
    "MSN116": "invalid-expectation",
    "MSN117": "invalid-name",
    "MSN118": "invalid-delete-when",
    "MSN119": "invalid-sequence-by",
    "MSN120": "duplicate-config-file",
    "MSN121": "unlisted-domain-folder",
    "MSN201": "unresolved-logical-name",
    "MSN202": "duplicate-table",
    "MSN203": "unparseable-sql",
    "MSN204": "computed-table-name",
    "MSN205": "real-table-name",
    "MSN206": "file-read",
    "MSN207": "raw-string-placeholder",
    "MSN208": "model-cycle",
    "MSN901": "usage-error",
    "MSN902": "unknown-environment",
    "MSN903": "databricks-cli-missing",
    "MSN904": "databricks-command-failed",
    "MSN905": "unexpected-error",
    "MSN906": "pipeline-column-not-found",
    "MSN907": "expectation-failed",
    "MSN908": "pipeline-failed",
}


def test_no_rule_id_is_removed_reused_or_changes_meaning():
    assert {code: rule.name for code, rule in RULES.items()} == REGISTERED_RULES


def test_rule_ids_are_msn_plus_three_digits_with_one_name_each():
    assert all(re.fullmatch(r"MSN\d{3}", rule) for rule in RULES)
    assert len({rule.name for rule in RULES.values()}) == len(RULES)


def test_an_unregistered_rule_can_not_be_reported():
    with pytest.raises(KeyError):
        error("MSN999", "", "A message.", "A fix.")


def replacing(file: str, old: str, new: str) -> Callable[[Path], None]:
    def change(project: Path) -> None:
        path = project / file
        assert old in path.read_text()
        path.write_text(path.read_text().replace(old, new))

    return change


SOURCE = "domains/sales/sources/orders.yaml"
MODEL = "domains/sales/models/fct_orders"


def seed(column: str, rows: str | None, name: str = "countries") -> Callable[[Path], None]:
    def declare(project: Path) -> None:
        folder = project / "domains/sales/seeds"
        folder.mkdir()
        config = f"kind: seed\nversion: 1\nfile: {name}.csv\ncolumns:\n  {column}\n"
        (folder / f"{name}.yaml").write_text(config)
        if rows is not None:
            (folder / f"{name}.csv").write_text(rows)

    return declare


INVALID_PROJECTS = {
    "MSN101": replacing(SOURCE, "kind: source\n", ""),
    "MSN102": replacing(SOURCE, "kind: source\n", "kind: sauce\n"),
    "MSN103": replacing(SOURCE, "version: 1\n", ""),
    "MSN104": replacing(SOURCE, "version: 1\n", "version: 2\n"),
    "MSN105": replacing(SOURCE, "kind: source\n", "kind: model\n"),
    "MSN106": replacing(SOURCE, "format: json\n", "format: 7\n"),
    "MSN107": lambda project: (project / SOURCE).write_text("just a string"),
    "MSN108": lambda project: (project / f"{MODEL}.yaml").unlink(),
    "MSN109": lambda project: (project / f"{MODEL}.sql").unlink(),
    "MSN110": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  keys: [order_id]\n"),
    "MSN111": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  scd: 2\n"),
    "MSN112": seed("code: STRING", None),
    "MSN113": seed("code: STRING", "nope\nAU\n"),
    "MSN114": seed("code: INT", "code\nAU\n"),
    "MSN115": seed("code: VARCAHR", "code\nAU\n"),
    "MSN116": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  expectations:\n    - name: bad\n      expect: amount >\n",
    ),
    "MSN117": seed("code: STRING", "code\nAU\n", name="vat-rates"),
    "MSN118": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at\n"
        "  delete_when: op =\n",
    ),
    "MSN119": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at DESC\n",
    ),
    "MSN120": lambda project: (project / SOURCE.replace(".yaml", ".yml")).write_text(
        (project / SOURCE).read_text()
    ),
    "MSN121": lambda project: (project / "domains/hr").mkdir(),
    "MSN201": lambda project: (project / f"{MODEL}.sql").write_text("SELECT * FROM a.b.c"),
    "MSN202": seed("code: STRING", "code\nAU\n", name="orders"),
    "MSN203": lambda project: (project / f"{MODEL}.sql").write_text("SELECT FROM WHERE"),
    "MSN204": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM IDENTIFIER(:table)"
    ),
    "MSN205": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM dev_sales.silver.orders"
    ),
    "MSN206": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM read_files('/Volumes/x')"
    ),
    "MSN207": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT r'${env}' AS x FROM sales.silver.orders"
    ),
    "MSN208": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM sales.gold.fct_orders"
    ),
}


@pytest.mark.parametrize(("rule", "break_project"), INVALID_PROJECTS.items())
def test_every_project_rule_reports_a_message_and_a_fix_and_exits_1(
    project: Path, rule: str, break_project: Callable[[Path], None]
):
    break_project(project)

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == rule
    assert diagnostic["name"] == RULES[rule].name
    assert diagnostic["severity"] == "error"
    assert diagnostic["message"]
    assert diagnostic["fix"]
    assert diagnostic["docs"] == DOCS


def test_a_new_rule_must_be_tested_here():
    """The tests above, and the refresh failure tests, cover these by name. A new rule joins one."""
    usage_and_environment = {"MSN901", "MSN902", "MSN903", "MSN904", "MSN905"}
    refresh_failures = {"MSN906", "MSN907", "MSN908"}

    assert set(RULES) == set(INVALID_PROJECTS) | usage_and_environment | refresh_failures


def test_the_docs_state_every_exit_code_and_every_rule():
    docs = (Path(__file__).parent.parent / "docs/reference/json-output.md").read_text()

    assert "| 0 | Clean" in docs
    assert "| 1 | Rule failures" in docs
    assert "| 2 | Usage or environment error" in docs
    for code, rule in RULES.items():
        assert f"| [`{code}`](rules/{code.lower()}.md) | `{rule.name}` |" in docs


def test_help_states_the_exit_codes():
    result = runner.invoke(app, ["--help"])

    assert "0 clean, 1 rule failures, 2 usage or environment error" in result.stdout
