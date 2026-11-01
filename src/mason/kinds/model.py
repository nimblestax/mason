"""A Gold Model: a dataset built from SQL that reads Logical Names."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Model:
    domain: str
    name: str
    sql: str
    file: Path


def load(domain: str, file: Path) -> Model:
    return Model(domain=domain, name=file.stem, sql=file.read_text(), file=file)


def generate(model: Model, target: str, sql: str) -> str:
    return f"CREATE OR REFRESH MATERIALIZED VIEW {target} AS\n{sql}"
