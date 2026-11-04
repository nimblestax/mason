"""A Seed: small reference data kept as a file in Git, with a declared schema."""

import csv
import re
from collections.abc import Callable
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mason.diagnostics import Diagnostic, error
from mason.kinds.base import STRICT, ColumnName, ExactInteger, InDomain
from mason.statements import listed, statement

KIND = "seed"
FOLDER = "seeds"

WHOLE_NUMBER = re.compile(r"[+-]?\d{1,19}")
NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")
DECIMAL_VALUE = re.compile(r"[+-]?(\d*)\.?(\d*)")
DECIMAL_TYPE = re.compile(r"DECIMAL(?:\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\))?")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIMESTAMP_NTZ = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d{1,6})?")
TIMESTAMP = re.compile(TIMESTAMP_NTZ.pattern + r"(Z|[+-]\d{2}:\d{2})?")


class SeedV1(InDomain):
    """Small reference data kept in Git and fully replaced on each deploy."""

    model_config = ConfigDict(**STRICT, title="Mason Seed")

    kind: Literal["seed"] = Field(description="The Kind of this file.")
    version: Annotated[Literal[1], ExactInteger] = Field(
        description="The schema version of this Kind."
    )
    file: str = Field(
        pattern=r"^[^/\\]+\.csv$", description="The data file, in the same folder as this file."
    )
    columns: dict[ColumnName, str] = Field(
        min_length=1,
        # Without it, the schema would let a column name that isn't an identifier through.
        json_schema_extra={"additionalProperties": False},
        description="Each column's name and SQL type. An empty value in the file is NULL.",
    )

    @property
    def data_file(self) -> Path:
        return self.config_file.parent / self.file

    @property
    def rows(self) -> tuple[tuple[str | None, ...], ...]:
        """The data in the declared column order, for a Seed whose data has passed its checks."""
        header, rows = _read(self.data_file)
        positions = [header.index(name) for name in self.columns]
        return tuple(tuple(cells[at] or None for at in positions) for _, cells in rows)


VERSIONS: dict[int, type[BaseModel]] = {1: SeedV1}
Seed = SeedV1

# `UPGRADES[n]` turns version n into version n + 1.
UPGRADES: dict[int, Callable[[Any], BaseModel]] = {}


def problems(root: Path, folder: Path, seeds: list[Seed]) -> list[Diagnostic]:
    """Problems with each Seed's data file."""
    return [problem for seed in seeds for problem in _data_problems(root, seed)]


def _data_problems(root: Path, seed: Seed) -> list[Diagnostic]:
    relative_config = seed.config_file.relative_to(root).as_posix()
    if not seed.data_file.is_file():
        return [_missing_file(relative_config, seed.file)]
    unsupported = [t for t in seed.columns.values() if not _is_supported(t)]
    if unsupported:
        return [_unsupported_type(relative_config, t) for t in unsupported]
    relative_data = seed.data_file.relative_to(root).as_posix()
    try:
        header, rows = _read(seed.data_file)
    except (UnicodeDecodeError, csv.Error) as problem:
        return [_unreadable(relative_data, problem)]
    if sorted(header) != sorted(seed.columns):
        return [_wrong_header(relative_data, header, list(seed.columns))]
    return [
        found
        for line, cells in rows
        for found in _row_problems(relative_data, line, header, cells, seed.columns)
    ]


def generate(seed: Seed, target: str) -> str:
    """The rows live in the definition, so any edit to the file replaces the whole table."""
    found = seed.rows
    no_rows = (None,) * len(seed.columns)
    columns = seed.columns.items()
    sql = statement(
        f"CREATE OR REFRESH MATERIALIZED VIEW {target}",
        "AS SELECT",
        listed(f"CAST(`{name}` AS {sql_type}) AS `{name}`" for name, sql_type in columns),
        "FROM VALUES",
        listed(f"({', '.join(map(_literal, row))})" for row in found or (no_rows,)),
        f"AS seed({', '.join(f'`{name}`' for name in seed.columns)})",
        _empty_filter(found),
    )
    return sql + "\n"


def _empty_filter(rows: tuple[tuple[str | None, ...], ...]) -> str | None:
    """With no rows, one row of NULLs gives the columns their types, and this filters it out."""
    return None if rows else "WHERE false"


def _read(data: Path) -> tuple[list[str], list[tuple[int, list[str]]]]:
    # `utf-8-sig`, because spreadsheets often save CSV with a byte order mark.
    with data.open(newline="", encoding="utf-8-sig") as opened:
        reader = csv.reader(opened, strict=True)
        header = next(reader, [])
        return header, [(reader.line_num, cells) for cells in reader if cells]


def _row_problems(
    file: str, line: int, header: list[str], cells: list[str], columns: dict[str, str]
) -> list[Diagnostic]:
    if len(cells) != len(header):
        return [_wrong_length(file, line, len(cells), len(header))]
    return [
        _wrong_value(file, line, name, value, columns[name])
        for name, value in zip(header, cells, strict=True)
        if value and not _fits(value, columns[name])
    ]


def _is_supported(sql_type: str) -> bool:
    return _normal(sql_type) in CHECKS or _decimal(sql_type) is not None


def _fits(value: str, sql_type: str) -> bool:
    decimal = _decimal(sql_type)
    if decimal:
        return _is_decimal(value, *decimal)
    return CHECKS[_normal(sql_type)](value)


def _normal(sql_type: str) -> str:
    return sql_type.strip().upper()


def _decimal(sql_type: str) -> tuple[int, int] | None:
    """Precision and scale, which Databricks defaults to 10 and 0."""
    match = DECIMAL_TYPE.fullmatch(_normal(sql_type))
    if not match:
        return None
    precision, scale = int(match[1] or 10), int(match[2] or 0)
    return (precision, scale) if 1 <= precision <= 38 and scale <= precision else None


def _is_decimal(value: str, precision: int, scale: int) -> bool:
    match = DECIMAL_VALUE.fullmatch(value)
    if not match or not (match[1] or match[2]):
        return False
    whole, fraction = match[1].lstrip("0"), match[2].rstrip("0")
    return len(whole) <= precision - scale and len(fraction) <= scale


def _is_whole_number(bits: int, value: str) -> bool:
    limit = 2 ** (bits - 1)
    return WHOLE_NUMBER.fullmatch(value) is not None and -limit <= int(value) < limit


def _is_number(value: str) -> bool:
    return NUMBER.fullmatch(value) is not None


def _is_boolean(value: str) -> bool:
    return value.lower() in ("true", "false")


def _is_date(value: str) -> bool:
    return DATE.fullmatch(value) is not None and _parses(date.fromisoformat, value)


def _is_timestamp(shape: re.Pattern[str], value: str) -> bool:
    return shape.fullmatch(value) is not None and _parses(datetime.fromisoformat, value)


def _parses(parse: Callable[[str], object], value: str) -> bool:
    try:
        parse(value)
    except ValueError:
        return False
    return True


CHECKS: dict[str, Callable[[str], bool]] = {
    "STRING": lambda _: True,
    "BOOLEAN": _is_boolean,
    "TINYINT": partial(_is_whole_number, 8),
    "SMALLINT": partial(_is_whole_number, 16),
    "INT": partial(_is_whole_number, 32),
    "INTEGER": partial(_is_whole_number, 32),
    "BIGINT": partial(_is_whole_number, 64),
    "FLOAT": _is_number,
    "DOUBLE": _is_number,
    "DATE": _is_date,
    "TIMESTAMP": partial(_is_timestamp, TIMESTAMP),
    "TIMESTAMP_NTZ": partial(_is_timestamp, TIMESTAMP_NTZ),
}


def _literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    # Escaped so a value can't read as a pipeline placeholder, which is substituted inside strings.
    return "'" + escaped.replace("${", "\\u0024{") + "'"


def _missing_file(file: str, data: str) -> Diagnostic:
    return error(
        "MSN112",
        file,
        f"`{data}` doesn't exist beside this file.",
        "Correct `file`, or add the data file to the same folder.",
    )


def _wrong_header(file: str, header: list[str], columns: list[str]) -> Diagnostic:
    found = ", ".join(header) or "nothing"
    return error(
        "MSN113",
        file,
        f"The first line has {found}, but the Seed declares {', '.join(columns)}.",
        "Make the first line name each declared column once, or change `columns`.",
        1,
    )


def _wrong_length(file: str, line: int, found: int, expected: int) -> Diagnostic:
    return error(
        "MSN114",
        file,
        f"This row has {found} values, but the Seed has {expected} columns.",
        "Give the row one value per column. Quote any value that contains a comma.",
        line,
    )


def _wrong_value(file: str, line: int, column: str, value: str, sql_type: str) -> Diagnostic:
    return error(
        "MSN114",
        file,
        f"`{column}` is `{value}`, which isn't a valid {sql_type}.",
        f"Correct the value, or change the type of `{column}` in the Seed's config file.",
        line,
    )


def _unsupported_type(file: str, sql_type: str) -> Diagnostic:
    supported = ", ".join((*CHECKS, "DECIMAL(precision, scale)"))
    return error(
        "MSN115",
        file,
        f"Mason can't check a Seed's values against `{sql_type}`.",
        f"Use one of: {supported}.",
    )


def _unreadable(file: str, problem: Exception) -> Diagnostic:
    return error(
        "MSN107",
        file,
        f"This file can't be read as CSV: {problem}",
        "Save the file as UTF-8, and close every quoted value.",
    )
