"""The `mason` command. Commands stay thin and work on one loaded Project."""

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import wraps
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from pydantic import BaseModel, Field
from typer.core import TyperGroup

from mason import output, scaffold
from mason.build import compiler
from mason.check import rules
from mason.deploy import deploy as delivery
from mason.deploy.databricks import DatabricksCli
from mason.diagnostics import EXIT_CODES, USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error
from mason.kinds import KINDS, latest_schema, platform
from mason.load import config, project

EPILOG = (
    "Exit codes: "
    + ", ".join(f"{code} {meaning.split(':')[0].lower()}" for code, meaning in EXIT_CODES.items())
    + "."
)


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


app = typer.Typer(cls=ReportingGroup, no_args_is_help=True, add_completion=False, epilog=EPILOG)


class Ci(StrEnum):
    github = "github"


ProjectOption = Annotated[Path, typer.Option("--project", help="The project folder.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON envelope.")]


@dataclass(frozen=True)
class Outcome[Result: BaseModel]:
    """What a command that succeeded tells a person, and tells a machine.

    A command's return annotation names its Result, which the reference documents.
    """

    text: str
    result: Result


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
                typer.echo(output.envelope(label, True, outcome.result.model_dump(), []))
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
        typer.echo(output.envelope(label, False, {}, failure.diagnostics))
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


class Created(BaseModel):
    project: str = Field(description="The folder the project was created in.")


@command()
def init(
    ci: Annotated[Ci, typer.Option("--ci", help="CI provider to write files for.")] = Ci.github,
    host: Annotated[str, typer.Option("--host", help="Workspace URL.")] = scaffold.PLACEHOLDER_HOST,
    root: ProjectOption = Path("."),
) -> Outcome[Created]:
    """Create a working project."""
    scaffold.write_project(root, host, ci.value)
    return Outcome(f"Created a Mason project in {root}", Created(project=str(root)))


class Valid(BaseModel):
    """Empty: `validate` reports what it finds as diagnostics."""


@command()
def validate(root: ProjectOption = Path(".")) -> Outcome[Valid]:
    """Check config and SQL references, with no workspace."""
    problems = rules.check(project.load(root))
    if problems:
        raise Failure(problems)
    return Outcome("Valid.", Valid())


class KindSchema(BaseModel):
    kind: str = Field(description="The Kind described.")
    version: int = Field(description="The newest version of the Kind this Mason supports.")
    json_schema: dict[str, Any] = Field(description="The Kind's JSON Schema at that version.")


@command()
def schema(
    kind: Annotated[str, typer.Argument(help="The Kind to describe.")],
) -> Outcome[KindSchema]:
    """Print a Kind's fields from the installed Mason. Needs no project."""
    if kind not in KINDS:
        raise Failure([config.unknown_kind(kind, "")], USAGE_OR_ENVIRONMENT)
    version, json_schema = latest_schema(kind)
    result = KindSchema(kind=kind, version=version, json_schema=json_schema)
    return Outcome(output.fields(kind, version, json_schema), result)


class Package(BaseModel):
    """Without `--env`, `compile` writes the generated code."""

    package: str = Field(description="The folder the generated code was written to.")


class Sql(BaseModel):
    """With `--env`, `compile` prints it instead."""

    env: str = Field(description="The Environment the SQL is for.")
    sql: str = Field(description="Every generated file as runnable SQL for that Environment.")


@command("compile")
def compile_(
    env: Annotated[
        str | None, typer.Option("--env", help="Print runnable SQL for this Environment.")
    ] = None,
    root: ProjectOption = Path("."),
) -> Outcome[Package | Sql]:
    """Write generated code, or print it for one Environment."""
    loaded = project.load(root)
    if env:
        _require_environment(loaded, env)
        sql = compiler.print_for(loaded, env)
        return Outcome(sql, Sql(env=env, sql=sql))
    package = compiler.write_package(loaded)
    return Outcome(f"Wrote {package}", Package(package=str(package)))


class Deployed(BaseModel):
    env: str = Field(description="The Environment deployed and refreshed.")


@command()
def deploy(
    env: Annotated[str, typer.Option("--env", help="The Environment to deploy.")],
    root: ProjectOption = Path("."),
) -> Outcome[Deployed]:
    """Deploy to an Environment and refresh its tables."""
    loaded = project.load(root)
    _require_environment(loaded, env)
    delivery.deploy(loaded, env, DatabricksCli())
    return Outcome(f"Deployed to {env}", Deployed(env=env))
