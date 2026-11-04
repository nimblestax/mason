"""Every Kind. A new Databricks object is a new module registered in this list."""

from typing import Any

from mason.kinds import model, platform, seed, source

KINDS = {module.KIND: module for module in (source, seed, model, platform)}

# The Kinds whose files live in a Domain's folder, in the order they're loaded.
IN_DOMAINS = (source, seed, model)


def json_schemas(kind: str) -> dict[int, dict[str, Any]]:
    """The JSON Schema of each version of a Kind, generated from its models."""
    return {n: version.model_json_schema() for n, version in KINDS[kind].VERSIONS.items()}


def latest_schema(kind: str) -> tuple[int, dict[str, Any]]:
    """A Kind's newest version and its JSON Schema: what `mason schema` and its page describe."""
    return max(json_schemas(kind).items())


def versions(kind: str) -> list[int]:
    return sorted(KINDS[kind].VERSIONS)
