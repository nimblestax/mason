"""Every Kind. A new Databricks object is a new module registered in this list."""

from typing import Any

from mason.kinds import model, platform, seed, source

KINDS = {module.KIND: module for module in (source, seed, model, platform)}


def json_schemas(kind: str) -> dict[int, dict[str, Any]]:
    """The JSON Schema of each version of a Kind, generated from its models where it has them."""
    if kind == platform.KIND:
        return {n: version.model_json_schema() for n, version in platform.VERSIONS.items()}
    return {source.KIND: source, seed.KIND: seed, model.KIND: model}[kind].SCHEMAS


def versions(kind: str) -> list[int]:
    return sorted(json_schemas(kind))
