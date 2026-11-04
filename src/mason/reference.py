"""Writes the generated reference pages into the docs folder, from the code they describe."""

import json
import sys
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

from mason.kinds import KINDS, latest_schema
from mason.registry import RULES, Example, Rule

WAY = "https://nimblestax.com/way"
LANGUAGES = {".yaml": "yaml", ".yml": "yaml", ".sql": "sql", ".csv": "csv"}


def write(docs: Path) -> None:
    rules = docs / "reference/rules"
    rules.mkdir(parents=True, exist_ok=True)
    for code, rule in RULES.items():
        (rules / f"{code.lower()}.md").write_text(_rule_page(code, rule))
    kinds = docs / "reference/kinds"
    kinds.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        (kinds / f"{kind}.md").write_text(_kind_page(kind))


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


def _front_matter(title: str, description: str) -> str:
    fields = {
        "title": title,
        "description": description,
        "generated": True,
        "mason_version": version("mason-databricks"),
    }
    return f"---\n{yaml.safe_dump(fields, sort_keys=False, width=1000)}---\n"


if __name__ == "__main__":
    write(Path(sys.argv[1]))
