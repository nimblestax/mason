"""Loads a Project from disk. A file's Domain comes from its folder (ADR 0006)."""

from dataclasses import dataclass
from pathlib import Path

from mason.kinds import model, platform, source
from mason.kinds.model import Model
from mason.kinds.platform import Platform
from mason.kinds.source import Source


@dataclass(frozen=True)
class Project:
    root: Path
    platform: Platform
    sources: tuple[Source, ...]
    models: tuple[Model, ...]


def load(root: Path) -> Project:
    contract = platform.load(root)
    sources: list[Source] = []
    models: list[Model] = []
    for domain in contract.domains:
        folder = root / "domains" / domain
        sources += [source.load(domain, f) for f in sorted(folder.glob("sources/*.yaml"))]
        models += [model.load(domain, f) for f in sorted(folder.glob("models/*.sql"))]
    return Project(root, contract, tuple(sources), tuple(models))
