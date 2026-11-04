"""Checks SQL written in config before it goes into generated code.

It imports nothing else from Mason, so a Kind's model can use it.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

DIALECT = "databricks"


def row_condition_problem(condition: str) -> str | None:
    """Why `condition` isn't one SQL condition that sees only its own row, if it isn't."""
    return _one_row_problem(condition, "condition")


def row_expression_problem(expression: str) -> str | None:
    """Why `expression` isn't one SQL expression that sees only its own row, if it isn't."""
    return _one_row_problem(expression, "expression")


def _one_row_problem(sql: str, what: str) -> str | None:
    try:
        statements = [tree for tree in sqlglot.parse(sql, dialect=DIALECT) if tree]
    except SqlglotError:
        return "It doesn't parse as SQL."
    if len(statements) != 1:
        return f"It holds {len(statements)} statements, not one {what}."
    [tree] = statements
    if isinstance(tree, exp.Query) or tree.find(exp.Query):
        return "It holds a query, which reads other rows."
    if tree.find(exp.AggFunc, exp.Window):
        return "It uses an aggregate or window function, which reads other rows."
    # Mason wraps the SQL in generated code, so a `--` comment would hide what follows it.
    if any(node.comments for node in tree.walk()):
        return "It holds a comment."
    # `updated_at DESC` parses as `updated_at` named `DESC`, which no generated clause accepts.
    if isinstance(tree, exp.Alias):
        return f"It names its result `{tree.alias}`, which isn't part of one {what}."
    return None
