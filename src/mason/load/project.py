"""Loads a Project from disk: finds each Kind's files and has the Kind check what's beside them."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mason.diagnostics import Diagnostic
from mason.kinds import IN_DOMAINS, platform
from mason.kinds.base import InDomain
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
