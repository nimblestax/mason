"""A Source: a declared external dataset landed in bronze and conformed into silver."""

from dataclasses import dataclass
from pathlib import Path

import yaml

KIND = "source"
SCHEMAS = {
    1: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Mason Source",
        "description": "An external dataset landed in bronze and conformed into silver.",
        "type": "object",
        "required": ["kind", "version", "path", "format"],
        "additionalProperties": False,
        "properties": {
            "kind": {"const": "source", "description": "The Kind of this file."},
            "version": {"const": 1, "description": "The schema version of this Kind."},
            "path": {
                "type": "string",
                "minLength": 1,
                "description": "Where the files land, such as a Unity Catalog Volume path.",
            },
            "format": {
                "enum": ["avro", "binaryFile", "csv", "json", "orc", "parquet", "text", "xml"],
                "description": "The format of the files at `path`.",
            },
            "silver": {
                "type": "object",
                "additionalProperties": False,
                "description": (
                    "How silver is written, with `keys`, `sequence_by`, `scd` and `delete_when`. "
                    "With no keys, it is append-only."
                ),
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "uniqueItems": True,
                        "description": "The columns that identify a row, which turn on upserts.",
                    },
                    "sequence_by": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The column or expression that orders changes to a key.",
                    },
                    "delete_when": {
                        "type": "string",
                        "minLength": 1,
                        "description": "A SQL condition that marks a change as a delete.",
                    },
                    "scd": {
                        "enum": [1, 2],
                        "description": "1 keeps the latest row per key, 2 keeps every version.",
                    },
                },
            },
        },
    }
}


@dataclass(frozen=True)
class Silver:
    keys: tuple[str, ...] = ()
    sequence_by: str | None = None
    scd: int = 1
    delete_when: str | None = None


@dataclass(frozen=True)
class Source:
    domain: str
    name: str
    path: str
    format: str
    silver: Silver = Silver()


def load(domain: str, file: Path) -> Source:
    config = yaml.safe_load(file.read_text())
    silver = config.get("silver", {})
    return Source(
        domain=domain,
        name=file.stem,
        path=config["path"],
        format=config["format"],
        silver=Silver(
            keys=tuple(silver.get("keys", ())),
            sequence_by=silver.get("sequence_by"),
            scd=silver.get("scd", 1),
            delete_when=silver.get("delete_when"),
        ),
    )


def generate(source: Source, bronze: str, silver: str) -> str:
    """Bronze keeps every row as it landed and can't be reset, so it can always be replayed."""
    return f"""CREATE OR REFRESH STREAMING TABLE {bronze}
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('{source.path}', format => '{source.format}');

{_silver(source, bronze, silver)}"""


def _silver(source: Source, bronze: str, silver: str) -> str:
    if not source.silver.keys:
        return f"""CREATE OR REFRESH STREAMING TABLE {silver}
AS SELECT *
FROM STREAM({bronze});
"""
    delete = (
        f"APPLY AS DELETE WHEN {source.silver.delete_when}\n" if source.silver.delete_when else ""
    )
    return f"""CREATE OR REFRESH STREAMING TABLE {silver};

CREATE FLOW upsert_{source.name} AS AUTO CDC INTO {silver}
FROM STREAM({bronze})
KEYS ({", ".join(source.silver.keys)})
{delete}SEQUENCE BY {source.silver.sequence_by}
STORED AS SCD TYPE {source.silver.scd};
"""
