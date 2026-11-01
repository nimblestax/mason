"""Project rules. `mason validate` runs these with no workspace."""

from dataclasses import asdict, dataclass

from mason import sql
from mason.names import LogicalName
from mason.project import Project


@dataclass(frozen=True)
class Diagnostic:
    rule: str
    name: str
    severity: str
    file: str
    line: int | None
    message: str
    fix: str
    docs: str

    def as_dict(self) -> dict:
        return asdict(self)


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
    return Diagnostic(
        rule="MSN201",
        name="unresolved-logical-name",
        severity="error",
        file=file.relative_to(project.root).as_posix(),
        line=None,
        message=f"{logical} isn't a table in this project.",
        fix="Declare a Source or Gold Model with this name, or correct the Logical Name.",
        docs="",
    )
