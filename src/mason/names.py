"""Name mapping: the only module that builds a real table name."""

import re
from dataclasses import dataclass

from mason.kinds.source import Source
from mason.project import Project

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


def path_placeholder(source: Source) -> str:
    """Where a Source's files land as generated code refers to it, the same in every Environment."""
    return f"${{{_path_setting(source)}}}"


def settings(project: Project, env: str) -> dict[str, str]:
    """The value of every placeholder in one Environment."""
    platform = project.platform
    values = {}
    for domain in platform.domains:
        for layer in (*platform.source_layers, *platform.model_layers):
            parts = {"env": env, "domain": domain, "layer": layer}
            values[f"catalog_{domain}_{layer}"] = platform.catalog_pattern.format(**parts)
            values[f"schema_{domain}_{layer}"] = platform.schema_pattern.format(**parts)
    for source in project.sources:
        values[_path_setting(source)] = source.path_in(env)
    return values


def resolve(generated: str, project: Project, env: str) -> str:
    """Generated code with its placeholders replaced by one Environment's real names."""
    values = settings(project, env)
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], generated)


def _path_setting(source: Source) -> str:
    # The double underscore keeps `sales` + `eu_orders` apart from `sales_eu` + `orders`.
    return f"path_{source.domain}__{source.name}"
