"""Reads Logical Names out of Gold Model SQL and rewrites them, keeping the author's formatting."""

from collections.abc import Callable
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.tokens import Token, TokenType

from mason.names import LogicalName

DIALECT = "databricks"


@dataclass(frozen=True)
class Found:
    """Some text in the SQL and the line it starts on."""

    text: str
    line: int | None


@dataclass(frozen=True)
class Query:
    """What a Gold Model's SQL reads, and what in it can't be read as a Logical Name."""

    reads: dict[LogicalName, int | None] = field(default_factory=dict)
    unqualified: list[Found] = field(default_factory=list)
    computed: list[Found] = field(default_factory=list)


class Unparseable(Exception):
    """The SQL isn't one Databricks SQL query, so Mason can't tell what it reads."""

    def __init__(self, reason: str, line: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.line = line


def parse(sql: str) -> Query:
    """Fails closed: anything that might be a read but isn't a Logical Name is reported."""
    tree = _one_statement(sql)
    ctes = _cte_references(tree)
    query = Query()
    for table in tree.find_all(exp.Table):
        if any(table is cte for cte in ctes):
            continue
        line = table.this.meta.get("line")
        if _is_computed(table):
            query.computed.append(Found(table.this.sql(DIALECT), line))
            continue
        parts = _stream_parts(table) or table.parts
        if len(parts) == 3:
            query.reads.setdefault(LogicalName(*(part.name for part in parts)), line)
        elif all(isinstance(part, exp.Identifier) for part in parts):
            query.unqualified.append(Found(".".join(part.name for part in parts), line))
    return query


def reads(sql: str) -> set[LogicalName]:
    """Every three-part table the query reads. CTE names and aliases have no three-part name."""
    return set(parse(sql).reads)


def _one_statement(sql: str) -> exp.Expression:
    try:
        statements = [tree for tree in sqlglot.parse(sql, dialect=DIALECT) if tree]
    except ParseError as failure:
        [first, *_] = failure.errors
        raise Unparseable(
            f"It doesn't parse near `{first['highlight']}`.", first["line"]
        ) from failure
    except SqlglotError as failure:
        raise Unparseable(str(failure)) from failure
    if len(statements) != 1:
        raise Unparseable(f"It holds {len(statements)} statements, not one query.")
    return statements[0]


def _cte_references(tree: exp.Expression) -> list[exp.Table]:
    """Tables that name a CTE visible where they appear. A CTE's own body can't see it."""
    try:
        scopes = traverse_scope(tree)
    except SqlglotError as failure:
        raise Unparseable(str(failure)) from failure
    return [
        table
        for scope in scopes
        for table in scope.tables
        if len(table.parts) == 1 and table.name in scope.cte_sources
    ]


def _is_computed(table: exp.Table) -> bool:
    """`IDENTIFIER(...)` builds a name as the query runs, as does `STREAM` over anything else."""
    function = table.this
    if not isinstance(function, exp.Anonymous):
        return False
    if function.name.upper() == "IDENTIFIER":
        return True
    return function.name.upper() == "STREAM" and not _stream_parts(table)


def _stream_parts(table: exp.Table) -> list[exp.Expression]:
    """`STREAM(a.b.c)` parses as a function over a column; its parts are the table inside."""
    function = table.this
    if isinstance(function, exp.Anonymous) and function.name.upper() == "STREAM":
        if len(function.expressions) == 1 and isinstance(function.expressions[0], exp.Column):
            return function.expressions[0].parts
    return []


def rewrite(sql: str, replacement: Callable[[LogicalName], str]) -> str:
    """Replaces each three-part name in place, so comments and layout survive."""
    tokens = sqlglot.tokenize(sql, dialect=DIALECT)
    known = reads(sql)
    pieces: list[str] = []
    position = 0
    for first, second, third in _three_part_names(tokens):
        name = LogicalName(first.text, second.text, third.text)
        if name in known:
            pieces += [sql[position : first.start], replacement(name)]
            position = third.end + 1
    return "".join(pieces) + sql[position:]


def _three_part_names(tokens: list[Token]) -> list[tuple[Token, Token, Token]]:
    found = []
    for index in range(len(tokens) - 4):
        first, dot_one, second, dot_two, third = tokens[index : index + 5]
        if dot_one.token_type == TokenType.DOT and dot_two.token_type == TokenType.DOT:
            found.append((first, second, third))
    return found
