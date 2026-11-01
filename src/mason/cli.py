"""The `mason` command. Commands stay thin and work on one loaded Project."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from mason import compiler, config, output, project, rules, scaffold
from mason import deploy as delivery
from mason.databricks import DatabricksCli, WorkspaceError
from mason.diagnostics import Diagnostic
from mason.kinds import KINDS

app = typer.Typer(no_args_is_help=True, add_completion=False)


class Ci(StrEnum):
    github = "github"


ProjectOption = Annotated[Path, typer.Option("--project", help="The project folder.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON envelope.")]


@app.command()
def init(
    ci: Annotated[Ci, typer.Option("--ci", help="CI provider to write files for.")] = Ci.github,
    host: Annotated[str, typer.Option("--host", help="Workspace URL.")] = scaffold.PLACEHOLDER_HOST,
    root: ProjectOption = Path("."),
) -> None:
    """Create a working project."""
    scaffold.write_project(root, host, ci.value)
    typer.echo(f"Created a Mason project in {root}")


@app.command()
def validate(root: ProjectOption = Path("."), as_json: JsonOption = False) -> None:
    """Check config and SQL references, with no workspace."""
    try:
        diagnostics = rules.check(project.load(root))
    except config.InvalidConfig as error:
        diagnostics = error.diagnostics
    if as_json:
        found = [diagnostic.as_dict() for diagnostic in diagnostics]
        typer.echo(output.envelope("validate", not diagnostics, {}, found))
    else:
        for diagnostic in diagnostics:
            _print(diagnostic)
        typer.echo("Invalid." if diagnostics else "Valid.")
    if diagnostics:
        raise typer.Exit(1)


@app.command()
def schema(
    kind: Annotated[str, typer.Argument(help="The Kind to describe.")],
    as_json: JsonOption = False,
) -> None:
    """Print a Kind's fields from the installed Mason. Needs no project."""
    if kind not in KINDS:
        problem = config.unknown_kind(kind, "")
        if as_json:
            typer.echo(output.envelope("schema", False, {}, [problem.as_dict()]))
        else:
            _print(problem)
        raise typer.Exit(2)
    version, json_schema = max(KINDS[kind].SCHEMAS.items())
    if as_json:
        result = {"kind": kind, "version": version, "json_schema": json_schema}
        typer.echo(output.envelope("schema", True, result, []))
    else:
        typer.echo(output.fields(kind, version, json_schema))


@app.command("compile")
def compile_(
    env: Annotated[
        str | None, typer.Option("--env", help="Print runnable SQL for this Environment.")
    ] = None,
    root: ProjectOption = Path("."),
) -> None:
    """Write generated code, or print it for one Environment."""
    loaded = _load(root)
    if env:
        typer.echo(compiler.print_for(loaded, env))
    else:
        typer.echo(f"Wrote {compiler.write_package(loaded)}")


@app.command()
def deploy(
    env: Annotated[str, typer.Option("--env", help="The Environment to deploy.")],
    root: ProjectOption = Path("."),
) -> None:
    """Deploy to an Environment and refresh its tables."""
    try:
        delivery.deploy(_load(root), env, DatabricksCli())
    except delivery.InvalidProject as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    except WorkspaceError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error


def _load(root: Path) -> project.Project:
    try:
        return project.load(root)
    except config.InvalidConfig as error:
        for diagnostic in error.diagnostics:
            _print(diagnostic)
        raise typer.Exit(1) from error


def _print(diagnostic: Diagnostic) -> None:
    where = f" {diagnostic.file}" if diagnostic.file else ""
    typer.echo(f"{diagnostic.rule}{where}: {diagnostic.message}")
    typer.echo(f"  Fix: {diagnostic.fix}")
