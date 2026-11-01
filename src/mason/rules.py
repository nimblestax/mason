"""Project rules. `mason validate` runs these with no workspace."""

from mason import sql
from mason.diagnostics import Diagnostic, error
from mason.names import LogicalName
from mason.project import Project


def check(project: Project) -> list[Diagnostic]:
    known = _tables(project)
    diagnostics = []
    for model in project.models:
        for read in sorted(sql.reads(model.sql), key=str):
            if read not in known:
                diagnostics.append(_unresolved(project, model.file, read))
    return diagnostics


def _tables(project: Project) -> set[LogicalName]:
    tables = set()
    for source in project.sources:
        for layer in project.platform.source_layers:
            tables.add(LogicalName(source.domain, layer, source.name))
    for model in project.models:
        tables.add(LogicalName(model.domain, project.platform.model_layers[-1], model.name))
    return tables


def _unresolved(project: Project, file, read: LogicalName) -> Diagnostic:
    logical = f"{read.domain}.{read.layer}.{read.entity}"
    return error(
        "MSN201",
        file.relative_to(project.root).as_posix(),
        f"{logical} isn't a table in this project.",
        "Declare a Source or Gold Model with this name, or correct the Logical Name.",
    )
