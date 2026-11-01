"""The `mason` command. Commands stay thin and work on one loaded Project."""

import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import wraps
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from typer.core import TyperGroup

from mason import compiler, config, output, project, rules, scaffold
from mason import deploy as delivery
from mason.databricks import DatabricksCli
from mason.diagnostics import USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error
from mason.kinds import KINDS, platform

EXIT_CODES = "Exit codes: 0 clean, 1 rule failures, 2 usage or environment error."


class ReportingGroup(TyperGroup):
    """Reports a usage error as an envelope, because it stops a command before its code runs."""

    def invoke(self, ctx: Any) -> Any:
        as_json = "--json" in ctx.args
        try:
            return super().invoke(ctx)
        except typer.TyperException as problem:
            if not as_json:
                raise
            stopped = getattr(problem, "ctx", None)
            label = stopped.info_name if stopped not in (None, ctx) else None
            fix = f"Run `mason {label} --help`." if label else "Run `mason --help`."
            found = error("MSN901", "", problem.format_message(), fix)
            _report_failure(label or "usage", True, Failure([found], USAGE_OR_ENVIRONMENT))


app = typer.Typer(cls=ReportingGroup, no_args_is_help=True, add_completion=False, epilog=EXIT_CODES)


class Ci(StrEnum):
    github = "github"


ProjectOption = Annotated[Path, typer.Option("--project", help="The project folder.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON envelope.")]


@dataclass(frozen=True)
class Outcome:
    """What a command that succeeded tells a person, and tells a machine."""

    text: str
    result: dict[str, Any] = field(default_factory=dict)


def command(name: str | None = None) -> Callable:
    """Registers a command, which gets `--json` and returns an Outcome or raises a Failure."""

    def register(run: Any) -> Any:
        label = name or run.__name__

        def finish(*args: Any, as_json: bool = False, **kwargs: Any) -> None:
            try:
                outcome = run(*args, **kwargs)
            except Failure as failure:
                _report_failure(label, as_json, failure)
            except Exception as problem:  # Keeps the exit-code contract when Mason itself breaks.
                traceback.print_exc()
                _report_failure(label, as_json, _unexpected(problem))
            if as_json:
                typer.echo(output.envelope(label, True, outcome.result, []))
            else:
                typer.echo(outcome.text)

        json_parameter = Parameter(
            "as_json", Parameter.KEYWORD_ONLY, default=False, annotation=JsonOption
        )
        parameters = [*signature(run).parameters.values(), json_parameter]
        # Typer reads the options from this signature, so `--json` needs no line in any command.
        wrapped: Any = wraps(run)(finish)
        wrapped.__signature__ = signature(run).replace(
            parameters=parameters, return_annotation=None
        )
        wrapped.__annotations__ = {**run.__annotations__, "as_json": JsonOption}
        return app.command(label)(wrapped)

    return register


def _report_failure(label: str, as_json: bool, failure: Failure) -> NoReturn:
    if as_json:
        found = [diagnostic.as_dict() for diagnostic in failure.diagnostics]
        typer.echo(output.envelope(label, False, {}, found))
    else:
        for diagnostic in failure.diagnostics:
            _print(diagnostic)
    raise typer.Exit(failure.exit_code)


def _unexpected(problem: Exception) -> Failure:
    found = error(
        "MSN905",
        "",
        f"Mason stopped unexpectedly: {problem}",
        "Read the traceback on stderr. If your machine isn't the cause, report a bug.",
    )
    return Failure([found], USAGE_OR_ENVIRONMENT)


def _require_environment(loaded: project.Project, env: str) -> None:
    known = sorted(loaded.platform.hosts)
    if env not in known:
        found = error(
            "MSN902",
            platform.FILE_NAME,
            f"`{env}` isn't an Environment in this project.",
            f"Use one of: {', '.join(known)}.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)


def _print(diagnostic: Diagnostic) -> None:
    where = f" {diagnostic.file}" if diagnostic.file else ""
    typer.echo(f"{diagnostic.rule}{where}: {diagnostic.message}")
    typer.echo(f"  Fix: {diagnostic.fix}")


@command()
def init(
    ci: Annotated[Ci, typer.Option("--ci", help="CI provider to write files for.")] = Ci.github,
    host: Annotated[str, typer.Option("--host", help="Workspace URL.")] = scaffold.PLACEHOLDER_HOST,
    root: ProjectOption = Path("."),
) -> Outcome:
    """Create a working project."""
    scaffold.write_project(root, host, ci.value)
    return Outcome(f"Created a Mason project in {root}", {"project": str(root)})


@command()
def validate(root: ProjectOption = Path(".")) -> Outcome:
    """Check config and SQL references, with no workspace."""
    problems = rules.check(project.load(root))
    if problems:
        raise Failure(problems)
    return Outcome("Valid.")


@command()
def schema(kind: Annotated[str, typer.Argument(help="The Kind to describe.")]) -> Outcome:
    """Print a Kind's fields from the installed Mason. Needs no project."""
    if kind not in KINDS:
        raise Failure([config.unknown_kind(kind, "")], USAGE_OR_ENVIRONMENT)
    version, json_schema = max(KINDS[kind].SCHEMAS.items())
    result = {"kind": kind, "version": version, "json_schema": json_schema}
    return Outcome(output.fields(kind, version, json_schema), result)


@command("compile")
def compile_(
    env: Annotated[
        str | None, typer.Option("--env", help="Print runnable SQL for this Environment.")
    ] = None,
    root: ProjectOption = Path("."),
) -> Outcome:
    """Write generated code, or print it for one Environment."""
    loaded = project.load(root)
    if env:
        _require_environment(loaded, env)
        sql = compiler.print_for(loaded, env)
        return Outcome(sql, {"env": env, "sql": sql})
    package = compiler.write_package(loaded)
    return Outcome(f"Wrote {package}", {"package": str(package)})


@command()
def deploy(
    env: Annotated[str, typer.Option("--env", help="The Environment to deploy.")],
    root: ProjectOption = Path("."),
) -> Outcome:
    """Deploy to an Environment and refresh its tables."""
    loaded = project.load(root)
    _require_environment(loaded, env)
    delivery.deploy(loaded, env, DatabricksCli())
    return Outcome(f"Deployed to {env}", {"env": env})
