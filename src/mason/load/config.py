"""Checks a config file against its Kind before anything reads it."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from mason.diagnostics import RULES, Diagnostic, Failure, error
from mason.kinds import KINDS, versions


class InvalidConfig(Failure):
    pass


def load[M: BaseModel](root: Path, file: Path, expected: str, latest: type[M]) -> M:
    """A file of the `expected` Kind, checked against its own version and upgraded to `latest`."""
    result = read(root, file, expected)
    if isinstance(result, list):
        raise InvalidConfig(result)
    if not isinstance(result, latest):
        raise TypeError(f"`{expected}` upgrades to {type(result).__name__}, not {latest.__name__}.")
    return result


def read(root: Path, file: Path, expected: str) -> list[Diagnostic] | BaseModel:
    """The file's problems, or its content at the latest version of its Kind."""
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
    return _validate(relative, kind, content)


def _validate(relative: str, kind: str, content: dict) -> list[Diagnostic] | BaseModel:
    """Checks the file with its own version's model, then upgrades it to the latest version."""
    module = KINDS[kind]
    version = _version_number(content["version"])
    if version not in module.VERSIONS:
        return [_unknown_version(relative, kind, content["version"], sorted(module.VERSIONS))]
    try:
        document = module.VERSIONS[version].model_validate(content)
    except ValidationError as problems:
        return [_diagnostic(relative, kind, item) for item in problems.errors()]
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


def unknown_kind(kind: object, file: str) -> Diagnostic:
    known = ", ".join(sorted(KINDS))
    return error(
        "MSN102",
        file,
        f"`{kind}` isn't a Kind.",
        f"Use one of: {known}.",
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


def _diagnostic(file: str, kind: str, problem: Any) -> Diagnostic:
    """A cross-field check carries its own rule. Any other problem is an MSN106 on one field."""
    if problem["type"] in RULES:
        return error(problem["type"], file, problem["msg"], problem["ctx"]["fix"])
    field = ".".join(map(str, problem["loc"]))
    prefix = f"{field}: " if field else ""
    return error(
        "MSN106",
        file,
        f"{prefix}{problem['msg']}",
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
