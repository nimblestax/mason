"""How a generated SQL statement is laid out, so each Kind writes only which lines it has."""

from collections.abc import Iterable


def statement(*lines: str | None) -> str:
    """One SQL statement: the lines that apply, in order, ending in a semicolon."""
    return "\n".join(line for line in lines if line) + ";"


def listed(items: Iterable[str]) -> str:
    """Items one per line, indented under the clause that holds them."""
    return ",\n".join(f"  {item}" for item in items)


def string_literal(value: str) -> str:
    """`value` as a SQL string literal that reads back as exactly `value`."""
    return f"'{escaped(value)}'"


def escaped(value: str) -> str:
    """`value` escaped to sit between the quotes of a SQL string literal."""
    text = value.replace("\\", "\\\\").replace("'", "\\'")
    # So a value can't read as a pipeline placeholder, which is substituted inside strings.
    return text.replace("${", "\\u0024{")
