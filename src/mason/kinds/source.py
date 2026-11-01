"""A Source: a declared external dataset landed in bronze and conformed into silver."""

from dataclasses import dataclass
from pathlib import Path

import yaml


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
