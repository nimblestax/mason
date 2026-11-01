"""Reads Logical Names out of Gold Model SQL and rewrites them, keeping the author's formatting."""

from collections.abc import Callable

import sqlglot
from sqlglot import exp
from sqlglot.tokens import Token, TokenType

from mason.names import LogicalName

DIALECT = "databricks"


def reads(sql: str) -> set[LogicalName]:
    """Every three-part table the query reads. CTE names and aliases have no three-part name."""
    tree = sqlglot.parse_one(sql, dialect=DIALECT)
    return {
        LogicalName(table.catalog, table.db, table.name)
        for table in tree.find_all(exp.Table)
        if table.catalog
    }


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
