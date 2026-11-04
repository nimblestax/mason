"""Writes the generated reference pages into the docs folder, from the code they describe."""

import json
import sys
from collections.abc import Iterator
from importlib.metadata import version
from inspect import unwrap
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

import yaml
from pydantic import BaseModel, TypeAdapter
from typer.core import TyperArgument, TyperCommand, TyperOption
from typer.main import get_command

from mason import output
from mason.cli import app
from mason.diagnostics import EXIT_CODES, Diagnostic, error
from mason.kinds import KINDS, latest_schema
from mason.registry import RULES, Example, Rule

WAY = "https://nimblestax.com/way"
LANGUAGES = {".yaml": "yaml", ".yml": "yaml", ".sql": "sql", ".csv": "csv"}
EXAMPLE = error(
    "MSN201",
    "domains/sales/models/fct_orders.sql",
    "sales.silver.nope isn't a table in this project.",
    "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
)


def write(docs: Path) -> None:
    rules = docs / "reference/rules"
    rules.mkdir(parents=True, exist_ok=True)
    for code, rule in RULES.items():
        (rules / f"{code.lower()}.md").write_text(_rule_page(code, rule))
    kinds = docs / "reference/kinds"
    kinds.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        (kinds / f"{kind}.md").write_text(_kind_page(kind))

    commands = docs / "reference/commands"
    commands.mkdir(parents=True, exist_ok=True)
    group: Any = get_command(app)
    callbacks = {info.name: info.callback for info in app.registered_commands}
    for name, registered in group.commands.items():
        page = _command_page(name, registered, _results(callbacks[name]))
        (commands / f"{name}.md").write_text(page)
    (docs / "reference/json-output.md").write_text(_json_page(group.commands))


def _kind_page(kind: str) -> str:
    version, schema = latest_schema(kind)
    title = schema["title"].removeprefix("Mason ")
    lead = (
        f"A file with `kind: {kind}`, at version {version}. `mason schema {kind}` prints the same"
        " fields from the Mason you installed.\n"
    )
    table = [
        "| Field | Type | Required | Default | Description |\n",
        "| --- | --- | --- | --- | --- |\n",
        *_field_rows(schema, schema.get("$defs", {}), ""),
    ]
    fields = "".join(table)
    return _front_matter(title, schema["description"]) + f"\n{lead}\n## Fields\n\n{fields}"


def _field_rows(schema: dict[str, Any], defs: dict[str, Any], prefix: str) -> Iterator[str]:
    """One table row per field of an object, each followed by the rows of the fields inside it."""
    for name, field in schema["properties"].items():
        required = "yes" if name in schema.get("required", []) else "no"
        default = f"`{_value(field['default'])}`" if "default" in field else ""
        cells = [f"`{prefix}{name}`", _type(field), required, default, field["description"]]
        yield "| " + " | ".join(cells) + " |\n"
        inner, path = _inner(_without_null(field), defs, f"{prefix}{name}")
        if inner:
            yield from _field_rows(inner, defs, path)


def _inner(field: dict[str, Any], defs: dict[str, Any], path: str) -> tuple[dict | None, str]:
    """The object a field holds, itself or as list items or map values, and its fields' prefix."""
    if "$ref" in field:
        return _resolve(field, defs), f"{path}."
    if "$ref" in field.get("items", {}):
        return _resolve(field["items"], defs), f"{path}[]."
    if "$ref" in (field.get("additionalProperties") or {}):
        return _resolve(field["additionalProperties"], defs), f"{path}.<name>."
    return None, path


def _resolve(field: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    return defs[field["$ref"].removeprefix("#/$defs/")]


def _type(field: dict[str, Any]) -> str:
    field = _without_null(field)
    if "const" in field:
        return f"`{field['const']}`"
    if "enum" in field:
        return "one of " + ", ".join(f"`{value}`" for value in field["enum"])
    if "$ref" in field:
        return "object"
    if field["type"] == "array":
        return f"list of {_type(field['items'])}"
    if field["type"] == "object":
        values = field.get("additionalProperties") or next(
            iter(field.get("patternProperties", {}).values())
        )
        return f"map of name to {_type(values)}"
    return field["type"]


def _value(value: Any) -> str:
    """A value as it's written in a Kind's YAML file."""
    return value if isinstance(value, str) else json.dumps(value)


def _without_null(field: dict[str, Any]) -> dict[str, Any]:
    """A field that may be null, as its type when it isn't. Its default shows it's optional."""
    if "anyOf" not in field:
        return field
    (kept,) = [option for option in field["anyOf"] if option.get("type") != "null"]
    return {**field, **kept}


def _json_page(commands: dict[str, TyperCommand]) -> str:
    example = output.envelope("validate", False, {}, [EXAMPLE])
    sections = [
        "Every `mason` command accepts `--json`. It prints one envelope on stdout and nothing"
        " else there. Logs, including the Databricks CLI's output, go to stderr.\n",
        f"```json\n{example}\n```\n",
        "## Envelope\n",
        *_shape(output.Envelope.model_json_schema(by_alias=True)),
        "## Diagnostics\n\nEach diagnostic in `diagnostics` is one problem found.\n",
        *_shape(TypeAdapter(Diagnostic).json_schema()),
        "## Results\n\nEach command's page describes its `result`.\n",
        "\n".join(
            f"- [`mason {name}`](commands/{name}.md): {registered.help}"
            for name, registered in commands.items()
        )
        + "\n",
        "## Exit codes\n\nEvery command exits with one of these.\n",
        _table(
            ["Code", "Meaning"], [f"| {code} | {meaning} |" for code, meaning in EXIT_CODES.items()]
        ),
        "## Rule IDs\n\nRule IDs are `MSN` plus three digits. An ID never changes meaning, and a"
        " retired ID is never reused. Each Rule's page says what it checks, why, an example that"
        " fails and the fix.\n",
        _table(
            ["Rule", "Name", "Meaning"],
            [
                f"| [`{code}`](rules/{code.lower()}.md) | `{rule.name}` | {rule.checks} |"
                for code, rule in RULES.items()
            ],
        ),
        "`mason schema <unknown kind>` reports `MSN102` and exits 2, because the mistake is on"
        " the command line. Every `MSN1xx` and `MSN2xx` rule exits 1 when found in a project.\n",
        "When `mason deploy` refreshes an Environment and a pipeline update fails, the"
        " diagnostic's `message` is the pipeline's own error, read from its event log: `MSN906`,"
        " `MSN907` or `MSN908`, each exiting 2. A pipeline retries a failed update once, so an"
        " error a retry can't fix is reported in about a minute. When no pipeline error can be"
        " read, Mason reports `MSN904` with the Databricks CLI's last lines.\n",
    ]
    description = "The envelope every command prints with --json, its exit codes and its rule IDs."
    front_matter = _front_matter("JSON output", description, redirects=["json-output"])
    return front_matter + "\n" + "\n".join(sections)


def _results(callback: Any) -> list[type[BaseModel]]:
    """The Result of each Outcome a command's return annotation names."""
    [result] = get_args(get_type_hints(unwrap(callback))["return"])
    return list(get_args(result)) if get_origin(result) is UnionType else [result]


def _command_page(name: str, registered: TyperCommand, results: list[type[BaseModel]]) -> str:
    arguments = [p for p in registered.params if isinstance(p, TyperArgument)]
    options = [p for p in registered.params if isinstance(p, TyperOption)]
    usage = " ".join(["mason", name, *(f"<{p.name}>" for p in arguments), "[OPTIONS]"])
    sections = [f"```console\n$ {usage}\n```\n"]
    if arguments:
        rows = [f"| `{p.name}` | {getattr(p, 'help', '')} |" for p in arguments]
        sections.append("## Arguments\n\n" + _table(["Argument", "Meaning"], rows))
    rows = [f"| `{p.opts[0]}` | {_takes(p)} | {_default(p)} | {p.help} |" for p in options]
    sections.append("## Options\n\n" + _table(["Option", "Takes", "Default", "Meaning"], rows))
    rows = [f"| {code} | {meaning} |" for code, meaning in EXIT_CODES.items()]
    sections.append("## Exit codes\n\n" + _table(["Code", "Meaning"], rows))
    sections.append(
        f"## JSON result\n\nWith `--json`, it prints the [envelope](../json-output.md) with"
        f" `schema` set to `mason.{name}/1`. When it succeeds, `result` is:\n"
    )
    for result in results:
        sections += _shape(result.model_json_schema(by_alias=True))
    return _front_matter(f"mason {name}", registered.help or "") + "\n" + "\n".join(sections)


def _takes(option: TyperOption) -> str:
    if option.is_flag:
        return "Nothing"
    choices = getattr(option.type, "choices", None)
    if choices:
        return ", ".join(f"`{choice}`" for choice in choices)
    return {"str": "text"}.get(option.type.name, option.type.name)


def _default(option: TyperOption) -> str:
    if option.required:
        return "Required"
    if option.is_flag or option.default is None:
        return ""
    return f"`{getattr(option.default, 'value', option.default)}`"


def _shape(json_schema: dict[str, Any]) -> list[str]:
    """A JSON object's fields, from the JSON Schema of the model that writes it, as sections."""
    sections = [f"{json_schema['description']}\n"] if "description" in json_schema else []
    rows = [
        f"| `{name}` | {_json_type(field)} | {field['description']} |"
        for name, field in json_schema["properties"].items()
    ]
    if rows:
        sections.append(_table(["Field", "Type", "Meaning"], rows))
    return sections


def _json_type(field: dict[str, Any]) -> str:
    if "anyOf" in field:
        return " or ".join(_json_type(option) for option in field["anyOf"])
    if "$ref" in field:
        return "object"
    if field["type"] == "array":
        return f"array of {_json_type(field['items'])}"
    return field["type"]


def _table(columns: list[str], rows: list[str]) -> str:
    header = f"| {' | '.join(columns)} |\n|{' --- |' * len(columns)}"
    return f"{header}\n" + "\n".join(rows) + "\n"


def _rule_page(code: str, rule: Rule) -> str:
    sections = [
        f"## What it checks\n\n{rule.checks}\n",
        f"## Why\n\n{rule.why}\n",
        f"## Example\n\n{_example(rule.example)}",
        f"## Fix\n\n{rule.fix}\n",
    ]
    if rule.principle:
        link = f"[{rule.principle.title}]({WAY}/{rule.principle.slug})"
        sections.append(f"## Principle\n\nThis Rule enforces {link}, from the Nimblestax Way.\n")
    return _front_matter(f"{code} {rule.name}", rule.checks) + "\n" + "\n".join(sections)


def _example(example: Example) -> str:
    if example.command:
        when = f"{example.when} " if example.when else ""
        return f"{when}In a project, this fails:\n\n```console\n$ {example.command}\n```\n"
    files = [
        f"`{path}`:\n\n```{LANGUAGES[Path(path).suffix]}\n{text}```\n"
        for path, text in example.files.items()
    ]
    these = "these files" if len(files) > 1 else "this file"
    lead = f"Write {these} into the project `mason init` creates, and `mason validate` fails:"
    return f"{lead}\n\n" + "\n".join(files)


def _front_matter(title: str, description: str, redirects: list[str] | None = None) -> str:
    fields: dict[str, Any] = {
        "title": title,
        "description": description,
        "generated": True,
        "mason_version": version("mason-databricks"),
    }
    if redirects:
        fields["redirects"] = redirects
    return f"---\n{yaml.safe_dump(fields, sort_keys=False, width=1000)}---\n"


if __name__ == "__main__":
    write(Path(sys.argv[1]))
