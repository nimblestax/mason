"""The `mason` command. Commands stay thin and work on one loaded Project."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from mason import compiler, output, project, rules, scaffold
from mason import deploy as delivery
from mason.databricks import DatabricksCli, WorkspaceError

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
    diagnostics = rules.check(project.load(root))
    if as_json:
        found = [diagnostic.as_dict() for diagnostic in diagnostics]
        typer.echo(output.envelope("validate", not diagnostics, {}, found))
    else:
        for diagnostic in diagnostics:
            typer.echo(f"{diagnostic.rule} {diagnostic.file}: {diagnostic.message}")
            typer.echo(f"  Fix: {diagnostic.fix}")
        typer.echo("Invalid." if diagnostics else "Valid.")
    if diagnostics:
        raise typer.Exit(1)


@app.command("compile")
def compile_(
    env: Annotated[
        str | None, typer.Option("--env", help="Print runnable SQL for this Environment.")
    ] = None,
    root: ProjectOption = Path("."),
) -> None:
    """Write generated code, or print it for one Environment."""
    loaded = project.load(root)
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
        delivery.deploy(project.load(root), env, DatabricksCli())
    except delivery.InvalidProject as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    except WorkspaceError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error
