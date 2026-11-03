"""Project rules. `mason validate` runs these with no workspace."""

from mason import names, sql
from mason.diagnostics import Diagnostic, error
from mason.names import LogicalName
from mason.project import Project


def check(project: Project) -> list[Diagnostic]:
    known = _tables(project)
    diagnostics = []
    for model in project.models:
        file = model.file.relative_to(project.root).as_posix()
        try:
            query = sql.parse(model.sql)
        except sql.Unparseable as failure:
            diagnostics.append(_unparseable(file, failure))
            continue
        diagnostics += _reads(project, known, file, query)
        diagnostics += [_unqualified(file, name) for name in query.unqualified]
        diagnostics += [_computed(file, computed) for computed in query.computed]
    return diagnostics + _seeds_named_like_sources(project)


def _reads(project: Project, known: set[LogicalName], file: str, query: sql.Query):
    """Every read must be a table in the project. A real table name gets its Logical Name."""
    diagnostics = []
    for read, line in sorted(query.reads.items(), key=lambda item: str(item[0])):
        if read in known:
            continue
        logical = names.logical_name_for(project, read)
        if logical:
            diagnostics.append(_real_name(file, read, logical, line))
        else:
            diagnostics.append(_unresolved(file, read, line))
    return diagnostics


def _tables(project: Project) -> set[LogicalName]:
    tables = set()
    for source in project.sources:
        for layer in project.platform.source_layers:
            tables.add(LogicalName(source.domain, layer, source.name))
    for seed in project.seeds:
        tables.add(LogicalName(seed.domain, project.platform.source_layers[1], seed.name))
    for model in project.models:
        tables.add(LogicalName(model.domain, project.platform.model_layers[-1], model.name))
    return tables


def _seeds_named_like_sources(project: Project) -> list[Diagnostic]:
    silver = project.platform.source_layers[1]
    sources = {(source.domain, source.name) for source in project.sources}
    return [
        error(
            "MSN202",
            seed.file.relative_to(project.root).as_posix(),
            f"{seed.domain}.{silver}.{seed.name} is both a Seed and a Source.",
            "Rename the Seed or the Source, so each has its own table.",
        )
        for seed in project.seeds
        if (seed.domain, seed.name) in sources
    ]


def _unresolved(file: str, read: LogicalName, line: int | None) -> Diagnostic:
    return error(
        "MSN201",
        file,
        f"{_dotted(read)} isn't a table in this project.",
        "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
        line,
    )


def _real_name(file: str, real: LogicalName, logical: LogicalName, line: int | None):
    return error(
        "MSN205",
        file,
        f"{_dotted(real)} is a real table name, which names one Environment.",
        f"Use its Logical Name, {_dotted(logical)}, so the same SQL works in every Environment.",
        line,
    )


def _dotted(name: LogicalName) -> str:
    return f"{name.domain}.{name.layer}.{name.entity}"


def _unqualified(file: str, name: sql.Found) -> Diagnostic:
    return error(
        "MSN201",
        file,
        f"`{name.text}` isn't a CTE or a Logical Name, so Mason can't tell which table it reads.",
        "Write the table as a three-part Logical Name, such as sales.silver.orders,"
        " or define a CTE with this name.",
        name.line,
    )


def _unparseable(file: str, failure: sql.Unparseable) -> Diagnostic:
    return error(
        "MSN203",
        file,
        f"Mason can't read this SQL, so it can't tell what it reads. {failure.reason}",
        "Make the file one Databricks SQL query that runs on its own.",
        failure.line,
    )


def _computed(file: str, computed: sql.Found) -> Diagnostic:
    return error(
        "MSN204",
        file,
        f"{computed.text} builds a table name as the query runs,"
        " so Mason can't see what it reads.",
        "Write the table as a Logical Name, such as sales.silver.orders,"
        " so every read shows in review.",
        computed.line,
    )
