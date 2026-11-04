"""Mason reads `.yml` config files, but every file it writes or ships ends in `.yaml`."""

from pathlib import Path

from typer.testing import CliRunner

from mason.cli import app

REPO = Path(__file__).parent.parent

runner = CliRunner()


def test_init_and_compile_write_no_yml_file(tmp_path: Path):
    assert runner.invoke(app, ["init", "--ci", "github", "--project", str(tmp_path)]).exit_code == 0
    assert runner.invoke(app, ["compile", "--project", str(tmp_path)]).exit_code == 0

    written = {file.relative_to(tmp_path).as_posix() for file in tmp_path.rglob("*.y*ml")}

    assert ".github/workflows/mason-merge.yaml" in written
    assert ".github/workflows/mason-pull-request.yaml" in written
    assert "build/databricks.yaml" in written
    assert not [file for file in written if file.endswith(".yml")]


def test_no_file_in_the_repo_ends_in_yml():
    tracked = [
        file.relative_to(REPO).as_posix()
        for folder in (".github", "src", "tests", "docs")
        for file in (REPO / folder).rglob("*.yml")
    ]

    assert tracked == []
