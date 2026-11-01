"""A Gold Model: a dataset built from SQL that reads Logical Names."""

from dataclasses import dataclass
from pathlib import Path

import yaml

KIND = "model"
SCHEMAS = {
    1: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Mason Gold Model",
        "description": "A dataset built from a SQL file that reads Logical Names.",
        "type": "object",
        "required": ["kind", "version", "sql"],
        "additionalProperties": False,
        "properties": {
            "kind": {"const": "model", "description": "The Kind of this file."},
            "version": {"const": 1, "description": "The schema version of this Kind."},
            "sql": {
                "type": "string",
                "pattern": "^[^/\\\\]+\\.sql$",
                "description": "The SQL file, in the same folder as this file.",
            },
        },
    }
}


@dataclass(frozen=True)
class Model:
    domain: str
    name: str
    sql: str
    file: Path


def load(domain: str, file: Path) -> Model:
    sql_file = file.parent / yaml.safe_load(file.read_text())["sql"]
    return Model(domain=domain, name=file.stem, sql=sql_file.read_text(), file=sql_file)


def generate(model: Model, target: str, sql: str) -> str:
    return f"CREATE OR REFRESH MATERIALIZED VIEW {target} AS\n{sql}"
