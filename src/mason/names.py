"""Name mapping: the only module that builds a real table name."""

import re
from dataclasses import dataclass

from mason.kinds.platform import Platform

PLACEHOLDER = re.compile(r"\$\{(\w+)\}")


@dataclass(frozen=True)
class LogicalName:
    domain: str
    layer: str
    entity: str


def placeholders(name: LogicalName) -> str:
    """The table as generated code refers to it, the same in every Environment."""
    suffix = f"{name.domain}_{name.layer}"
    return f"${{catalog_{suffix}}}.${{schema_{suffix}}}.{name.entity}"


def settings(platform: Platform, env: str) -> dict[str, str]:
    """The value of every placeholder in one Environment."""
    values = {}
    for domain in platform.domains:
        for layer in (*platform.source_layers, *platform.model_layers):
            parts = {"env": env, "domain": domain, "layer": layer}
            values[f"catalog_{domain}_{layer}"] = platform.catalog_pattern.format(**parts)
            values[f"schema_{domain}_{layer}"] = platform.schema_pattern.format(**parts)
    return values


def resolve(generated: str, platform: Platform, env: str) -> str:
    """Generated code with its placeholders replaced by one Environment's real names."""
    values = settings(platform, env)
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], generated)
