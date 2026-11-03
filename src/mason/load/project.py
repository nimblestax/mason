"""Loads a Project from disk. A file's Domain comes from its folder."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from mason.diagnostics import Diagnostic
from mason.kinds import model, platform, seed, source
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
    folders = {domain: root / "domains" / domain for domain in contract.domains}
    _require_valid([p for folder in folders.values() for p in _problems(root, folder)])
    sources: list[Source] = []
    seeds: list[Seed] = []
    models: list[Model] = []
    for domain, folder in folders.items():
        sources += [source.load(domain, f) for f in sorted(folder.glob("sources/*.yaml"))]
        seeds += [seed.load(domain, f) for f in sorted(folder.glob("seeds/*.yaml"))]
        models += [model.load(domain, f) for f in sorted(folder.glob("models/*.yaml"))]
    return Project(root, contract, tuple(sources), tuple(seeds), tuple(models))


def _problems(root: Path, folder: Path) -> list[Diagnostic]:
    problems: list[Diagnostic] = []
    for file in sorted(folder.glob("sources/*.yaml")):
        problems += _source_problems(root, file)
    for file in sorted(folder.glob("seeds/*.yaml")):
        problems += _seed_problems(root, file)
    for file in sorted(folder.glob("models/*.yaml")):
        problems += _model_problems(root, file)
    for file in sorted(folder.glob("models/*.sql")):
        if not file.with_suffix(".yaml").exists() and not _is_named_by_a_model(file):
            problems.append(config.sql_without_config(_relative(root, file), file.stem))
    return problems


def _source_problems(root: Path, file: Path) -> list[Diagnostic]:
    problems = config.check(root, file, source.KIND)
    if problems:
        return problems
    silver = yaml.safe_load(file.read_text()).get("silver", {})
    return config.silver_problems(_relative(root, file), silver)


def _seed_problems(root: Path, file: Path) -> list[Diagnostic]:
    return config.check(root, file, seed.KIND) or seed.problems(root, file)


def _model_problems(root: Path, file: Path) -> list[Diagnostic]:
    problems = config.check(root, file, model.KIND)
    if not problems:
        sql = yaml.safe_load(file.read_text())["sql"]
        if not (file.parent / sql).exists():
            problems.append(config.missing_sql(_relative(root, file), sql))
    return problems


def _is_named_by_a_model(sql_file: Path) -> bool:
    return any(config.names_sql(file, sql_file.name) for file in sql_file.parent.glob("*.yaml"))


def _relative(root: Path, file: Path) -> str:
    return file.relative_to(root).as_posix()


def _require_valid(problems: list[Diagnostic]) -> None:
    if problems:
        raise config.InvalidConfig(problems)
