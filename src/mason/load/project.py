"""Loads a Project from disk: finds each Kind's files and has the Kind check what's beside them."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mason.diagnostics import Diagnostic, error
from mason.kinds import IN_DOMAINS, platform
from mason.kinds.base import IDENTIFIER, InDomain
from mason.kinds.model import Model
from mason.kinds.platform import Platform
from mason.kinds.seed import Seed
from mason.kinds.source import Source
from mason.load import config


@dataclass(frozen=True)
class Project:
    root: Path
    platform: Platform
    sources: tuple[Source, ...]
    seeds: tuple[Seed, ...]
    models: tuple[Model, ...]


def load(root: Path) -> Project:
    contract = config.load(root, root / platform.FILE_NAME, platform.KIND, Platform)
    found: dict[str, list[Any]] = {kind.KIND: [] for kind in IN_DOMAINS}
    problems: list[Diagnostic] = []
    for domain in contract.domains:
        for kind in IN_DOMAINS:
            folder = root / "domains" / domain / kind.FOLDER
            # `Any`, because each Kind loads its own model.
            documents: list[Any] = []
            for file in sorted(folder.glob("*.yaml")):
                if not re.fullmatch(IDENTIFIER, file.stem):
                    problems.append(_invalid_name(root, file))
                    continue
                result = config.read(root, file, kind.KIND)
                if isinstance(result, list):
                    problems += result
                elif isinstance(result, InDomain):
                    documents.append(result.at(file))
            problems += kind.problems(root, folder, documents)
            found[kind.KIND] += documents
    if problems:
        raise config.InvalidConfig(problems)
    return Project(
        root,
        contract,
        tuple(found["source"]),
        tuple(found["seed"]),
        tuple(found["model"]),
    )


def _invalid_name(root: Path, file: Path) -> Diagnostic:
    """A table's name comes from its config file's name, and SQL takes it unquoted."""
    suggested = re.sub(r"[^A-Za-z0-9_]", "_", file.stem)
    if suggested[0].isdigit():
        suggested = f"_{suggested}"
    return error(
        "MSN117",
        file.relative_to(root).as_posix(),
        f"`{file.stem}` isn't a valid table name. It may hold only letters, digits and"
        " underscores, and may not start with a digit.",
        f"Rename the file to `{suggested}{file.suffix}`.",
    )
