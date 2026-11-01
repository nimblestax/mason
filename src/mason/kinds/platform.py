"""The Platform Contract: `mason.platform.yaml`."""

from dataclasses import dataclass
from pathlib import Path

import yaml

FILE_NAME = "mason.platform.yaml"
KIND = "platform"
SCHEMAS = {
    1: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Mason Platform Contract",
        "description": "The shared facts about a project's platform.",
        "type": "object",
        "required": ["kind", "version", "name", "environments", "naming", "domains"],
        "additionalProperties": False,
        "properties": {
            "kind": {"const": "platform", "description": "The Kind of this file."},
            "version": {"const": 1, "description": "The schema version of this Kind."},
            "name": {"type": "string", "minLength": 1, "description": "The project's name."},
            "environments": {
                "type": "object",
                "description": "Settings per Environment.",
                "minProperties": 1,
                "additionalProperties": {
                    "type": "object",
                    "required": ["host"],
                    "additionalProperties": False,
                    "properties": {"host": {"type": "string", "description": "Workspace URL."}},
                },
            },
            "naming": {
                "type": "object",
                "description": "How Logical Names map to real catalogs and schemas.",
                "required": ["catalog", "schema", "layers"],
                "additionalProperties": False,
                "properties": {
                    "catalog": {"type": "string", "description": "The catalog pattern."},
                    "schema": {"type": "string", "description": "The schema pattern."},
                    "layers": {
                        "type": "object",
                        "required": ["sources", "models"],
                        "additionalProperties": False,
                        "properties": {
                            "sources": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 2,
                                "maxItems": 2,
                                "description": "Exactly two source Layers, bronze then silver.",
                            },
                            "models": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "description": "One or more model Layers, read left to right.",
                            },
                        },
                    },
                },
            },
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
                "description": "The Domains, one folder each under `domains/`.",
            },
        },
    }
}


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
