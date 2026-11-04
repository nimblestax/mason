"""Generated output for a project in version 1 of every Kind, pinned byte for byte.

Each new version of a Kind is upgraded in memory before any stage sees it, and an upgrade must give
the same generated output. These files are what version 1 generates, so they must never change.
"""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()

FIXTURE = Path(__file__).parent / "fixtures" / "v1"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    copy = tmp_path / "project"
    shutil.copytree(FIXTURE / "project", copy)
    return copy


def files_under(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def test_the_compiled_package_is_unchanged(project: Path):
    result = runner.invoke(app, ["compile", "--project", str(project)])

    assert result.exit_code == 0, result.output
    assert files_under(project / "build") == files_under(FIXTURE / "expected" / "package")


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_the_sql_printed_for_each_environment_is_unchanged(project: Path, env: str):
    result = runner.invoke(app, ["compile", "--env", env, "--project", str(project)])

    assert result.exit_code == 0, result.output
    assert result.stdout == (FIXTURE / "expected" / f"{env}.sql").read_text()
