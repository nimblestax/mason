"""Name mapping: the only module that builds a real table name."""

import re
from dataclasses import dataclass

from mason.kinds.source import Source
from mason.load.project import Project

PLACEHOLDER = re.compile(r"\$\{(\w+)\}")


@dataclass(frozen=True)
class LogicalName:
    """Always lowercase, because Databricks matches names whatever their case."""

    domain: str
    layer: str
    entity: str

    def __post_init__(self) -> None:
        for part in ("domain", "layer", "entity"):
            object.__setattr__(self, part, getattr(self, part).lower())


def placeholders(name: LogicalName) -> str:
    """The table as generated code refers to it, the same in every Environment."""
    catalog = catalog_setting(name.domain, name.layer)
    schema = schema_setting(name.domain, name.layer)
    return f"${{{catalog}}}.${{{schema}}}.{name.entity}"


def catalog_setting(domain: str, layer: str) -> str:
    """The placeholder for a Domain and Layer's catalog, keyed in lowercase like Logical Names."""
    return f"catalog_{domain}_{layer}".lower()


def schema_setting(domain: str, layer: str) -> str:
    return f"schema_{domain}_{layer}".lower()


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
            values[catalog_setting(domain, layer)] = platform.naming.catalog_pattern.format(**parts)
            values[schema_setting(domain, layer)] = platform.naming.schema_pattern.format(**parts)
    for source in project.sources:
        values[_path_setting(source)] = source.path_in(env)
    return values


def logical_name_for(project: Project, real: LogicalName) -> LogicalName | None:
    """The Logical Name behind a real table name in any Environment, if it is one."""
    platform = project.platform
    for env in platform.hosts:
        values = settings(project, env)
        for domain in platform.domains:
            for layer in (*platform.source_layers, *platform.model_layers):
                catalog = values[catalog_setting(domain, layer)].lower()
                schema = values[schema_setting(domain, layer)].lower()
                if (real.domain, real.layer) == (catalog, schema):
                    return LogicalName(domain, layer, real.entity)
    return None


def resolve(generated: str, project: Project, env: str) -> str:
    """Generated code with its placeholders replaced by one Environment's real names.

    `${word}` that names no setting is the author's own text, so it stays as written.
    """
    values = settings(project, env)
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), generated)


def _path_setting(source: Source) -> str:
    # The double underscore keeps `sales` + `eu_orders` apart from `sales_eu` + `orders`.
    return f"path_{source.domain}__{source.name}"
