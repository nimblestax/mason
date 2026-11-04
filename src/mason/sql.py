"""Reads Logical Names out of Gold Model SQL and rewrites them, keeping the author's formatting."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.tokens import Token, TokenType

from mason.conditions import DIALECT
from mason.names import LogicalName

# Table-valued functions that read nothing, so a Gold Model may call them. Any other fails closed.
GENERATORS = {
    "range",
    "explode",
    "explode_outer",
    "posexplode",
    "posexplode_outer",
    "inline",
    "inline_outer",
    "stack",
    "json_tuple",
}
# Formats that read files straight from a path, as in parquet.`/Volumes/...`.
FILE_FORMATS = {"parquet", "json", "csv", "delta", "orc", "avro", "text", "binaryfile"}
# `${`, with the backslashes before it. An odd number escapes the `$`.
PLACEHOLDER_START = re.compile(r"(\\*)\$\{")
# How generated code writes `$`, so the pipeline never reads the author's text as a placeholder.
ESCAPED_DOLLAR = "\\u0024"


@dataclass(frozen=True)
class Found:
    """Some text in the SQL and the line it starts on."""

    text: str
    line: int | None


@dataclass(frozen=True)
class Query:
    """What a Gold Model's SQL reads, and what in it can't be read as a Logical Name."""

    reads: dict[LogicalName, Found] = field(default_factory=dict)  # Each as first written.
    unqualified: list[Found] = field(default_factory=list)
    computed: list[Found] = field(default_factory=list)
    file_reads: list[Found] = field(default_factory=list)
    raw_placeholders: list[Found] = field(default_factory=list)


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
    query = Query(raw_placeholders=_raw_placeholders(sql))
    for node in tree.find_all(exp.Table, exp.Stream):
        # A hint only steers the plan: it can't read a table, and one naming nothing is ignored.
        if any(node is cte for cte in ctes) or node.find_ancestor(exp.Hint):
            continue
        # `STREAM f(...)` without brackets parses as a Stream around f, so read it as `FROM f(...)`.
        table = node if isinstance(node, exp.Table) else exp.Table(this=node.this.copy())
        line = table.this.meta.get("line")
        if _is_computed(table):
            query.computed.append(Found(table.this.sql(DIALECT), line))
            continue
        parts = _stream_parts(table)
        function = None if parts else _function(table)
        if function:
            if function.lower() not in GENERATORS:
                query.file_reads.append(Found(function, line))
            continue
        parts = parts or table.parts
        written = Found(".".join(part.name for part in parts), line)
        if len(parts) == 3:
            query.reads.setdefault(LogicalName(*(part.name for part in parts)), written)
        elif _is_file_path(parts):
            file_format, path = parts
            query.file_reads.append(Found(f"{file_format.name}.`{path.name}`", line))
        elif all(isinstance(part, exp.Identifier) for part in parts):
            query.unqualified.append(written)
    return query


def _function(table: exp.Table) -> str | None:
    """The table-valued function a FROM item calls, qualified as written, if it calls one."""
    function = table.this
    if not isinstance(function, exp.Func):
        return None
    name = function.name if isinstance(function, exp.Anonymous) else function.sql_name()
    return ".".join([*(part.name for part in table.parts[:-1]), name])


def _is_file_path(parts: list[exp.Expression]) -> bool:
    """`parquet.`/Volumes/...`` reads files from a path, with no table at all."""
    if len(parts) != 2:
        return False
    file_format, path = parts
    return file_format.name.lower() in FILE_FORMATS and bool(path.args.get("quoted"))


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
    [statement] = statements
    # A top-level VALUES is a query too, but sqlglot doesn't class it as one.
    if not isinstance(statement, exp.Query | exp.Values):
        raise Unparseable(f"It's a {_keyword(statement)} statement, not a query.")
    return statement


def _keyword(statement: exp.Expression) -> str:
    """The word a statement starts with, such as DROP or INSERT."""
    if isinstance(statement, exp.Command):
        return statement.name.upper()
    if isinstance(statement, exp.TruncateTable):
        return "TRUNCATE"
    return statement.key.upper()


def _cte_references(tree: exp.Expression) -> list[exp.Table]:
    """Tables that name a CTE visible where they appear, in any case. A CTE's body can't see it."""
    try:
        scopes = traverse_scope(tree)
    except SqlglotError as failure:
        raise Unparseable(str(failure)) from failure
    return [
        table
        for scope in scopes
        for table in scope.tables
        if len(table.parts) == 1
        and table.name.lower() in {name.lower() for name in scope.cte_sources}
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
    known = reads(sql)
    pieces: list[str] = []
    position = 0
    for start, end, name in _three_part_names(sql):
        if name in known:
            pieces += [sql[position:start], replacement(name)]
            position = end
    return "".join(pieces) + sql[position:]


def _three_part_names(sql: str, offset: int = 0) -> list[tuple[int, int, LogicalName]]:
    """Each `a.b.c`, with where it starts and ends. Comments and strings aren't names."""
    tokens = sqlglot.tokenize(sql, dialect=DIALECT)
    found = []
    for index, token in enumerate(tokens):
        if token.token_type == TokenType.HINT:
            # A whole `/*+ ... */` is one token, so the names inside it are found in its body.
            body = token.start + len("/*+")
            found += _three_part_names(sql[body : token.end - 1], offset + body)
        window = tokens[index : index + 5]
        if len(window) == 5 and _is_three_part(window):
            first, _, second, _, third = window
            name = LogicalName(first.text, second.text, third.text)
            found.append((offset + first.start, offset + third.end + 1, name))
    return found


def _is_three_part(window: list[Token]) -> bool:
    return window[1].token_type == TokenType.DOT and window[3].token_type == TokenType.DOT


def escape_placeholders(sql: str) -> str:
    """Writes each `${` in a string or comment as `\\u0024{`, so the pipeline leaves it alone.

    Each string keeps its value. A raw string can't hold an escape, so it's left as written.
    """
    pieces: list[str] = []
    position = 0
    for token in sqlglot.tokenize(sql, dialect=DIALECT):
        # Between tokens is only whitespace and comments.
        pieces.append(_in_comment(sql[position : token.start]))
        text = sql[token.start : token.end + 1]
        if token.token_type == TokenType.STRING:
            text = PLACEHOLDER_START.sub(_escaped, text)
        elif token.token_type == TokenType.HINT:
            text = _in_comment(text)
        pieces.append(text)
        position = token.end + 1
    return "".join(pieces) + _in_comment(sql[position:])


def _in_comment(text: str) -> str:
    return text.replace("${", ESCAPED_DOLLAR + "{")


def _escaped(match: re.Match[str]) -> str:
    backslashes = match.group(1)
    # `\$` is already `$`, so its backslash goes, or the string would gain one.
    if len(backslashes) % 2:
        backslashes = backslashes[:-1]
    return backslashes + ESCAPED_DOLLAR + "{"


def _raw_placeholders(sql: str) -> list[Found]:
    """Raw strings holding `${`, which the pipeline would read as a placeholder."""
    return [
        Found(sql[token.start : token.end + 1], sql.count("\n", 0, token.start) + 1)
        for token in sqlglot.tokenize(sql, dialect=DIALECT)
        if token.token_type == TokenType.RAW_STRING and "${" in token.text
    ]
