"""Loads a Project from disk: finds each Kind's files and has the Kind check what's beside them."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mason.diagnostics import Diagnostic, error
from mason.kinds import IN_DOMAINS, platform
from mason.kinds.base import InDomain, config_files
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
    problems = _unlisted_domain_folders(root, contract.domains)
    for domain in contract.domains:
        for kind in IN_DOMAINS:
            folder = root / "domains" / domain / kind.FOLDER
            files, duplicates = _one_per_name(root, config_files(folder))
            problems += duplicates
            # `Any`, because each Kind loads its own model.
            documents: list[Any] = []
            for file in files:
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


def _one_per_name(root: Path, files: list[Path]) -> tuple[list[Path], list[Diagnostic]]:
    """A name's one config file. Both `orders.yaml` and `orders.yml` would be two tables."""
    by_name: dict[str, list[Path]] = {}
    for file in files:
        by_name.setdefault(file.stem, []).append(file)
    single = [found[0] for found in by_name.values() if len(found) == 1]
    both = [_duplicate(root, found) for found in by_name.values() if len(found) > 1]
    return single, both


def _duplicate(root: Path, files: list[Path]) -> Diagnostic:
    first, *rest = sorted(files, key=lambda file: file.suffix != ".yaml")
    return error(
        "MSN120",
        rest[-1].relative_to(root).as_posix(),
        f"{first.name} and {', '.join(file.name for file in rest)} both configure"
        f" {first.stem}, so Mason can't tell which one is meant.",
        "Keep one of them, and delete or rename the other.",
    )


def _unlisted_domain_folders(root: Path, domains: list[str]) -> list[Diagnostic]:
    """A folder under `domains/` is a Domain only if `domains` names it, in the same case."""
    folders = root / "domains"
    if not folders.is_dir():
        return []
    return [
        _unlisted(folder.name, domains)
        for folder in sorted(folders.iterdir())
        if folder.is_dir() and not folder.name.startswith(".") and folder.name not in domains
    ]


def _unlisted(folder: str, domains: list[str]) -> Diagnostic:
    file = f"domains/{folder}"
    same_but_case = [domain for domain in domains if domain.lower() == folder.lower()]
    if same_but_case:
        return error(
            "MSN121",
            file,
            f"`domains` in {platform.FILE_NAME} lists {same_but_case[0]}, not {folder}."
            " Only a file system that ignores case reads this folder for it.",
            f"Change {same_but_case[0]} to {folder} in `domains` in {platform.FILE_NAME},"
            " so it matches the folder's case.",
        )
    return error(
        "MSN121",
        file,
        f"`domains` in {platform.FILE_NAME} doesn't list {folder},"
        " so nothing in this folder is validated or deployed.",
        f"Add {folder} to `domains` in {platform.FILE_NAME}, matching the folder's case,"
        " or remove the folder.",
    )
