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
        },
    }
}


@dataclass(frozen=True)
class Source:
    domain: str
    name: str
    path: str
    format: str


def load(domain: str, file: Path) -> Source:
    config = yaml.safe_load(file.read_text())
    return Source(domain=domain, name=file.stem, path=config["path"], format=config["format"])


def generate(source: Source, bronze: str, silver: str) -> str:
    """Bronze keeps every row as it landed and can't be reset, so it can always be replayed."""
    return f"""CREATE OR REFRESH STREAMING TABLE {bronze}
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('{source.path}', format => '{source.format}');

CREATE OR REFRESH STREAMING TABLE {silver}
AS SELECT *
FROM STREAM({bronze});
"""
