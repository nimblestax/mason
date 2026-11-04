"""Checks a SQL condition written in config before it goes into generated code.

It imports nothing else from Mason, so a Kind's model can use it.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

DIALECT = "databricks"


def row_condition_problem(condition: str) -> str | None:
    """Why `condition` isn't one SQL condition that sees only its own row, if it isn't."""
    try:
        statements = [tree for tree in sqlglot.parse(condition, dialect=DIALECT) if tree]
    except SqlglotError:
        return "It doesn't parse as SQL."
    if len(statements) != 1:
        return f"It holds {len(statements)} statements, not one condition."
    [tree] = statements
    if isinstance(tree, exp.Query) or tree.find(exp.Query):
        return "It holds a query, which reads other rows."
    if tree.find(exp.AggFunc, exp.Window):
        return "It uses an aggregate or window function, which reads other rows."
    # Mason wraps the condition in generated code, so a `--` comment would hide what follows it.
    if any(node.comments for node in tree.walk()):
        return "It holds a comment."
    return None
