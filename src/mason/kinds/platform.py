"""The Platform Contract: `mason.platform.yaml`."""

from dataclasses import dataclass
from pathlib import Path

import yaml

FILE_NAME = "mason.platform.yaml"


@dataclass(frozen=True)
class Platform:
    name: str
    hosts: dict[str, str]
    catalog_pattern: str
    schema_pattern: str
    source_layers: tuple[str, str]
    model_layers: tuple[str, ...]
    domains: tuple[str, ...]


def load(root: Path) -> Platform:
    contract = yaml.safe_load((root / FILE_NAME).read_text())
    naming = contract["naming"]
    bronze, silver = naming["layers"]["sources"]
    return Platform(
        name=contract["name"],
        hosts={env: settings["host"] for env, settings in contract["environments"].items()},
        catalog_pattern=naming["catalog"],
        schema_pattern=naming["schema"],
        source_layers=(bronze, silver),
        model_layers=tuple(naming["layers"]["models"]),
        domains=tuple(contract["domains"]),
    )
