"""Checks a config file against its Kind before anything reads it."""

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from mason.diagnostics import Diagnostic, Failure, error
from mason.kinds import KINDS, json_schemas, platform, versions


class InvalidConfig(Failure):
    pass


def check(root: Path, file: Path, expected: str) -> list[Diagnostic]:
    """Problems with one file that should be of the `expected` Kind."""
    result = _read(root, file, expected)
    return result if isinstance(result, list) else []


def load[M: BaseModel](root: Path, file: Path, expected: str, latest: type[M]) -> M:
    """A file of the `expected` Kind, checked against its own version and upgraded to `latest`."""
    result = _read(root, file, expected)
    if isinstance(result, list):
        raise InvalidConfig(result)
    if not isinstance(result, latest):
        raise TypeError(f"`{expected}` upgrades to {type(result).__name__}, not {latest.__name__}.")
    return result


def _read(root: Path, file: Path, expected: str) -> list[Diagnostic] | BaseModel | dict:
    """The file's problems, or its content: a model at the latest version once a Kind has one."""
    relative = file.relative_to(root).as_posix()
    try:
        content = yaml.safe_load(file.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as problem:
        return [_unreadable(relative, problem)]
    if not isinstance(content, dict):
        return [_not_a_mapping(relative, expected)]
    if "kind" not in content:
        return [_missing_kind(relative, expected)]
    kind = content["kind"]
    if not isinstance(kind, str) or kind not in KINDS:
        return [unknown_kind(kind, relative)]
    if kind != expected:
        return [_wrong_kind(relative, kind, expected)]
    if "version" not in content:
        return [_missing_version(relative, kind)]
    # Only the Platform Contract has moved to Pydantic so far; the other Kinds follow.
    if kind == platform.KIND:
        return _validate(relative, kind, content)
    return _check_version_and_fields(relative, kind, content) or content


def _validate(relative: str, kind: str, content: dict) -> list[Diagnostic] | BaseModel:
    """Checks the file with its own version's model, then upgrades it to the latest version."""
    module = platform
    version = _version_number(content["version"])
    if version not in module.VERSIONS:
        return [_unknown_version(relative, kind, content["version"], sorted(module.VERSIONS))]
    try:
        document = module.VERSIONS[version].model_validate(content)
    except ValidationError as problems:
        return [_invalid_model_field(relative, kind, item) for item in problems.errors()]
    for step in range(version, max(module.VERSIONS)):
        document = module.UPGRADES[step](document)
    return document


def _version_number(version: object) -> int | None:
    """Which version's model to check against. That model still rejects `"1"` or `true`."""
    if isinstance(version, int):
        return int(version)
    if isinstance(version, str) and version.isdigit():
        return int(version)
    return None


def _check_version_and_fields(relative: str, kind: str, content: dict) -> list[Diagnostic]:
    version: Any = content["version"]
    schemas = json_schemas(kind)
    # `type` rather than isinstance, because YAML's `true` is an int to Python.
    if type(version) is not int or version not in schemas:
        return [_unknown_version(relative, kind, version, sorted(schemas))]
    validator = Draft202012Validator(schemas[version])
    found = sorted(validator.iter_errors(content), key=lambda item: list(item.absolute_path))
    return [_invalid_field(relative, kind, item) for item in found]


def unknown_kind(kind: object, file: str) -> Diagnostic:
    known = ", ".join(sorted(KINDS))
    return error(
        "MSN102",
        file,
        f"`{kind}` isn't a Kind.",
        f"Use one of: {known}.",
    )


def names_sql(file: Path, sql: str) -> bool:
    """Whether a model file names this SQL file, tolerating a file that's invalid in other ways."""
    try:
        content = yaml.safe_load(file.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    return isinstance(content, dict) and content.get("sql") == sql


def sql_without_config(file: str, stem: str) -> Diagnostic:
    return error(
        "MSN108",
        file,
        "This SQL file has no config file beside it.",
        f"Add `{stem}.yaml` beside it with `kind: model`, `version: 1` and `sql: {stem}.sql`.",
    )


def missing_sql(file: str, sql: str) -> Diagnostic:
    return error(
        "MSN109",
        file,
        f"`{sql}` doesn't exist beside this file.",
        "Correct `sql`, or add the SQL file to the same folder.",
    )


def silver_problems(file: str, silver: dict) -> list[Diagnostic]:
    """Fields of a Source's `silver:` block that only make sense together."""
    if "keys" in silver:
        return [] if "sequence_by" in silver else [_keys_without_sequence_by(file)]
    upsert_fields = ("sequence_by", "scd", "delete_when")
    return [_upsert_field_without_keys(file, name) for name in upsert_fields if name in silver]


def _keys_without_sequence_by(file: str) -> Diagnostic:
    return error(
        "MSN110",
        file,
        "`silver.keys` needs `silver.sequence_by`, to order the changes to each key.",
        "Add `sequence_by` with the column that orders changes, or remove `keys` to append.",
    )


def _upsert_field_without_keys(file: str, name: str) -> Diagnostic:
    return error(
        "MSN111",
        file,
        f"`silver.{name}` only applies to an upsert, and this Source has no `silver.keys`.",
        f"Add `keys` with the columns that identify a row, or remove `{name}` to append.",
    )


def _missing_kind(file: str, expected: str) -> Diagnostic:
    return error(
        "MSN101",
        file,
        "This file doesn't declare a `kind`.",
        f"Add `kind: {expected}` at the top of the file.",
    )


def _missing_version(file: str, kind: str) -> Diagnostic:
    latest = max(versions(kind))
    return error(
        "MSN103",
        file,
        "This file doesn't declare a `version`.",
        f"Add `version: {latest}` below `kind: {kind}`.",
    )


def _unknown_version(file: str, kind: str, version: object, known: list[int]) -> Diagnostic:
    return error(
        "MSN104",
        file,
        f"`{version}` isn't a version of `{kind}` in this Mason.",
        f"Use a version this Mason supports: {', '.join(map(str, known))}.",
    )


def _wrong_kind(file: str, kind: str, expected: str) -> Diagnostic:
    return error(
        "MSN105",
        file,
        f"This file says `kind: {kind}`, but Mason expects `{expected}` in this location.",
        f"Change it to `kind: {expected}`, or move the file to where `{kind}` files live.",
    )


def _invalid_field(file: str, kind: str, problem: Any) -> Diagnostic:
    return _msn106(file, kind, problem.absolute_path, problem.message)


def _invalid_model_field(file: str, kind: str, problem: Any) -> Diagnostic:
    return _msn106(file, kind, problem["loc"], problem["msg"])


def _msn106(file: str, kind: str, path: Any, message: str) -> Diagnostic:
    field = ".".join(map(str, path))
    prefix = f"{field}: " if field else ""
    return error(
        "MSN106",
        file,
        f"{prefix}{message}",
        f"Run `mason schema {kind}` to see the fields of this Kind.",
    )


def _unreadable(file: str, problem: Exception) -> Diagnostic:
    mark = getattr(problem, "problem_mark", None)
    return error(
        "MSN107",
        file,
        f"This file can't be read as YAML: {problem}",
        "Create the file, or correct its YAML.",
        mark.line + 1 if mark else None,
    )


def _not_a_mapping(file: str, expected: str) -> Diagnostic:
    return error(
        "MSN107",
        file,
        "This file isn't a YAML mapping of fields.",
        f"Start the file with `kind: {expected}` and its other fields.",
    )
