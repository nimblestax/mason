"""Project rules. `mason validate` runs these with no workspace."""

from mason import names, sql
from mason.diagnostics import Diagnostic, error
from mason.kinds.model import Model
from mason.load.project import Project
from mason.names import LogicalName


def check(project: Project) -> list[Diagnostic]:
    known = _tables(project)
    diagnostics = []
    reads: dict[LogicalName, set[LogicalName]] = {}
    for model in project.models:
        file = model.sql_file.relative_to(project.root).as_posix()
        try:
            query = sql.parse(model.query)
        except sql.Unparseable as failure:
            diagnostics.append(_unparseable(file, failure))
            continue
        reads[_gold(project, model)] = set(query.reads)
        diagnostics += _reads(project, known, file, query)
        diagnostics += [_unqualified(file, name) for name in query.unqualified]
        diagnostics += [_computed(file, computed) for computed in query.computed]
        diagnostics += [_file_read(file, found) for found in query.file_reads]
        diagnostics += [_raw_placeholder(file, found) for found in query.raw_placeholders]
    return (
        diagnostics
        + _cycles(project, reads)
        + _seeds_named_like_sources(project)
        + _named_like_a_quarantine(project)
    )


def _reads(project: Project, known: set[LogicalName], file: str, query: sql.Query):
    """Every read must be a table in the project. A real table name gets its Logical Name."""
    diagnostics = []
    for read, written in sorted(query.reads.items(), key=lambda item: str(item[0])):
        if read in known:
            continue
        logical = names.logical_name_for(project, read)
        if logical in known:
            diagnostics.append(_real_name(file, written, logical))
        elif logical:
            diagnostics.append(_real_name_of_no_table(file, written, logical))
        else:
            diagnostics.append(_unresolved(file, written))
    return diagnostics


def _gold(project: Project, model: Model) -> LogicalName:
    return LogicalName(model.domain, project.platform.model_layers[-1], model.name)


def _cycles(project: Project, reads: dict[LogicalName, set[LogicalName]]) -> list[Diagnostic]:
    """Each loop of Gold Models reading each other, found once by a depth-first walk."""
    files = {
        _gold(project, model): model.sql_file.relative_to(project.root).as_posix()
        for model in project.models
    }
    finished: set[LogicalName] = set()
    diagnostics = []

    def walk(model: LogicalName, path: list[LogicalName]) -> None:
        path.append(model)
        for read in sorted(reads[model] & reads.keys(), key=_dotted):
            if read in path:
                cycle = path[path.index(read) :]
                first = cycle.index(min(cycle, key=_dotted))
                diagnostics.append(_cycle(files, cycle[first:] + cycle[:first]))
            elif read not in finished:
                walk(read, path)
        path.pop()
        finished.add(model)

    for model in sorted(reads, key=_dotted):
        if model not in finished:
            walk(model, [])
    return sorted(diagnostics, key=lambda diagnostic: diagnostic.file)


def _cycle(files: dict[LogicalName, str], cycle: list[LogicalName]) -> Diagnostic:
    loop = " → ".join(_dotted(model) for model in [*cycle, cycle[0]])
    return error(
        "MSN208",
        files[cycle[0]],
        "A Gold Model can't read itself, directly or through other Gold Models,"
        f" because each must be built before it's read: {loop}.",
        "Remove one of these reads, so each Gold Model reads only tables built before it.",
    )


def _tables(project: Project) -> set[LogicalName]:
    tables = set()
    for source in project.sources:
        for layer in project.platform.source_layers:
            tables.add(LogicalName(source.domain, layer, source.name))
        if source.silver.quarantining:
            silver = project.platform.source_layers[1]
            tables.add(LogicalName(source.domain, silver, source.quarantine))
    for seed in project.seeds:
        tables.add(LogicalName(seed.domain, project.platform.source_layers[1], seed.name))
    for model in project.models:
        tables.add(_gold(project, model))
    return tables


def _seeds_named_like_sources(project: Project) -> list[Diagnostic]:
    silver = project.platform.source_layers[1]
    sources = {(source.domain, source.name) for source in project.sources}
    return [
        error(
            "MSN202",
            seed.config_file.relative_to(project.root).as_posix(),
            f"{seed.domain}.{silver}.{seed.name} is both a Seed and a Source.",
            "Rename the Seed or the Source, so each has its own table.",
        )
        for seed in project.seeds
        if (seed.domain, seed.name) in sources
    ]


def _named_like_a_quarantine(project: Project) -> list[Diagnostic]:
    """A Source's Quarantine table is in silver's schema, so no other table may take its name."""
    silver = project.platform.source_layers[1]
    quarantines = {
        (source.domain, source.quarantine): source.name
        for source in project.sources
        if source.silver.quarantining
    }
    return [
        error(
            "MSN202",
            table.config_file.relative_to(project.root).as_posix(),
            f"{table.domain}.{silver}.{table.name} is also the Quarantine table"
            f" of the Source {quarantines[(table.domain, table.name)]}.",
            "Rename this file, so each table has its own name.",
        )
        for table in (*project.sources, *project.seeds)
        if (table.domain, table.name) in quarantines
    ]


def _unresolved(file: str, read: sql.Found) -> Diagnostic:
    return error(
        "MSN201",
        file,
        f"{read.text} isn't a table in this project.",
        "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
        read.line,
    )


def _real_name(file: str, real: sql.Found, logical: LogicalName) -> Diagnostic:
    return error(
        "MSN205",
        file,
        f"{real.text} is a real table name, which names one Environment.",
        f"Use its Logical Name, {_dotted(logical)}, so the same SQL works in every Environment.",
        real.line,
    )


def _real_name_of_no_table(file: str, real: sql.Found, logical: LogicalName) -> Diagnostic:
    return error(
        "MSN205",
        file,
        f"{real.text} is a real table name, and no table called {_dotted(logical)}"
        " is in this project.",
        f"Declare a Source, Seed or Gold Model called {_dotted(logical)}, or correct the name.",
        real.line,
    )


def _file_read(file: str, found: sql.Found) -> Diagnostic:
    return error(
        "MSN206",
        file,
        f"{found.text} reads data that isn't a table in this project,"
        " so Mason can't check it or point it at each Environment.",
        "A Gold Model reads tables. Declare a Source for these files"
        " and read its silver table by Logical Name.",
        found.line,
    )


def _raw_placeholder(file: str, found: sql.Found) -> Diagnostic:
    return error(
        "MSN207",
        file,
        f"{found.text} holds `${{`, so the pipeline could replace it with a setting's value,"
        " and a raw string can't hold the escape that stops it.",
        "Write it as an ordinary string, doubling each backslash, and Mason escapes the `${`.",
        found.line,
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
