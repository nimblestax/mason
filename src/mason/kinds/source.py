"""A Source: a declared external dataset landed in bronze and conformed into silver."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from mason.conditions import row_condition_problem
from mason.diagnostics import Diagnostic
from mason.kinds.base import STRICT, ExactInteger, InDomain, unique
from mason.statements import listed, statement

KIND = "source"
FOLDER = "sources"

Text = Annotated[str, Field(min_length=1)]


class ExpectationV1(BaseModel):
    """A row-level rule on silver. A row meets it only when `expect` is true, not false or NULL."""

    model_config = STRICT

    name: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$",
        description="The rule's name, in snake_case. It is the reason a row is quarantined.",
    )
    expect: Text = Field(description="A SQL condition on one row that a good row meets.")
    action: Literal["warn", "quarantine", "fail"] = Field(
        default="quarantine",
        description=(
            "What happens to a row that fails: `warn` keeps it and counts it, `quarantine` keeps"
            " it out of silver in the Quarantine table, and `fail` stops the update."
        ),
    )

    @field_validator("expect")
    @classmethod
    def _expect_is_a_condition_on_one_row(cls, condition: str, info: ValidationInfo) -> str:
        problem = row_condition_problem(condition)
        if problem:
            raise PydanticCustomError(
                "MSN116",
                "Expectation `{name}` isn't a SQL condition on one row. {problem}",
                {
                    "name": info.data.get("name", "?"),
                    "problem": problem,
                    "fix": "Write `expect` as one condition on the row's own columns,"
                    " such as `amount > 0`. A rule across rows is a Test.",
                },
            )
        return condition


class SilverV1(BaseModel):
    """How silver is written. With no `keys`, it is append-only."""

    model_config = STRICT

    # `keys` comes first, so the checks of the fields after it can see it.
    keys: Annotated[list[Text], Field(min_length=1)] | None = Field(
        default=None,
        json_schema_extra={"uniqueItems": True},
        description="The columns that identify a row, which turn on upserts.",
    )
    # Checked even when it's left out, because `keys` needs it.
    sequence_by: Text | None = Field(
        default=None,
        validate_default=True,
        description="The column or expression that orders changes to a key.",
    )
    scd: Annotated[Literal[1, 2], ExactInteger] = Field(
        default=1, description="1 keeps the latest row per key, 2 keeps every version."
    )
    delete_when: Text | None = Field(
        default=None, description="A SQL condition that marks a change as a delete."
    )
    expectations: list[ExpectationV1] = Field(
        default_factory=list,
        description="Row-level rules each row of silver is checked against, in every Environment.",
    )

    @property
    def quarantining(self) -> list[ExpectationV1]:
        """The rules whose failing rows go to the Quarantine table instead of silver."""
        return [rule for rule in self.expectations if rule.action == "quarantine"]

    @field_validator("expectations")
    @classmethod
    def _expectation_names_are_unique(cls, rules: list[ExpectationV1]) -> list[ExpectationV1]:
        unique([rule.name for rule in rules], "Expectation name")
        return rules

    @field_validator("keys")
    @classmethod
    def _keys_are_unique(cls, keys: list[str] | None) -> list[str] | None:
        return None if keys is None else unique(keys, "key")

    @field_validator("sequence_by")
    @classmethod
    def _sequence_by_goes_with_keys(cls, value: str | None, info: ValidationInfo) -> str | None:
        if "keys" not in info.data:
            return value  # `keys` is invalid, and its own problem says so.
        if info.data["keys"] and value is None:
            # A rule ID as the error type reaches the user as that rule, with this fix.
            raise PydanticCustomError(
                "MSN110",
                "`silver.keys` needs `silver.sequence_by`, to order the changes to each key.",
                {
                    "fix": "Add `sequence_by` with the column that orders changes,"
                    " or remove `keys` to append."
                },
            )
        if not info.data["keys"] and value is not None:
            raise _upsert_field_without_keys("sequence_by")
        return value

    @field_validator("scd", "delete_when")
    @classmethod
    def _only_with_keys(cls, value: Any, info: ValidationInfo) -> Any:
        if "keys" in info.data and not info.data["keys"]:
            raise _upsert_field_without_keys(str(info.field_name))
        return value


def _upsert_field_without_keys(name: str) -> PydanticCustomError:
    return PydanticCustomError(
        "MSN111",
        "`silver.{name}` only applies to an upsert, and this Source has no `silver.keys`.",
        {
            "name": name,
            "fix": "Add `keys` with the columns that identify a row,"
            f" or remove `{name}` to append.",
        },
    )


class SourceV1(InDomain):
    """An external dataset landed in bronze and conformed into silver."""

    model_config = ConfigDict(**STRICT, title="Mason Source")

    kind: Literal["source"] = Field(description="The Kind of this file.")
    version: Annotated[Literal[1], ExactInteger] = Field(
        description="The schema version of this Kind."
    )
    path: str = Field(
        min_length=1,
        description=(
            "Where the files land, such as a Unity Catalog Volume path. "
            "`{env}` becomes the Environment's name."
        ),
    )
    format: Literal["avro", "binaryFile", "csv", "json", "orc", "parquet", "text", "xml"] = Field(
        description="The format of the files at `path`."
    )
    silver: SilverV1 = Field(
        default_factory=SilverV1,
        description=(
            "How silver is written, with `keys`, `sequence_by`, `scd` and `delete_when`. "
            "With no keys, it is append-only. `expectations` lists the rules each row must meet."
        ),
    )

    @property
    def quarantine(self) -> str:
        """The table in silver's schema that keeps the rows silver turns away."""
        return f"{self.name}_quarantine"

    def path_in(self, env: str) -> str:
        # Only `{env}`, because any other braces in a path are a glob for `read_files`.
        return self.path.replace("{env}", env)


VERSIONS: dict[int, type[BaseModel]] = {1: SourceV1}
Source = SourceV1

# `UPGRADES[n]` turns version n into version n + 1.
UPGRADES: dict[int, Callable[[Any], BaseModel]] = {}


def problems(root: Path, folder: Path, sources: list[Source]) -> list[Diagnostic]:
    """None: a Source has no files beside its config, so its fields are all there is to check."""
    return []


def generate(source: Source, path: str, bronze: str, silver: str, quarantine: str) -> str:
    """Bronze, the statements that write silver, then any Quarantine, with a blank line between."""
    statements = [_bronze(source, path, bronze), *_silver(source, bronze, silver)]
    held_back = source.silver.quarantining
    if held_back:
        statements.append(_quarantine(held_back, bronze, quarantine))
    return "\n\n".join(statements) + "\n"


def _bronze(source: Source, path: str, bronze: str) -> str:
    """Bronze keeps every row as it landed and can't be reset, so it can always be replayed."""
    return statement(
        f"CREATE OR REFRESH STREAMING TABLE {bronze}",
        "TBLPROPERTIES ('pipelines.reset.allowed' = 'false')",
        "AS SELECT *",
        f"FROM STREAM read_files('{path}', format => '{source.format}')",
    )


def _silver(source: Source, bronze: str, silver: str) -> list[str]:
    table = f"CREATE OR REFRESH STREAMING TABLE {silver}"
    if not source.silver.keys:
        return [_passing(table, source, bronze)]
    target = statement(table)
    if not source.silver.expectations:
        return [target, _upsert(source, bronze, silver)]
    # `FROM STREAM(...)` in Auto CDC takes only a table or view, so the checks go in a view.
    view = f"conformed_{source.name}"
    conformed = _passing(f"CREATE TEMPORARY VIEW {view}", source, bronze)
    return [target, conformed, _upsert(source, view, silver)]


def _passing(head: str, source: Source, bronze: str) -> str:
    """The rows of bronze that pass every quarantining rule, checked against the rest."""
    return statement(
        *_checked(head, source),
        "AS SELECT *",
        f"FROM STREAM({bronze})",
        _where_passed(source.silver.quarantining),
    )


def _checked(head: str, source: Source) -> list[str]:
    """A dataset's first line, with Lakeflow constraints for the rules that warn or fail."""
    constraints = [
        _constraint(rule) for rule in source.silver.expectations if rule.action != "quarantine"
    ]
    if not constraints:
        return [head]
    return [f"{head} (", listed(constraints), ")"]


def _constraint(rule: ExpectationV1) -> str:
    # With no ON VIOLATION, Lakeflow keeps the row and counts it in the table's metrics.
    violation = " ON VIOLATION FAIL UPDATE" if rule.action == "fail" else ""
    return f"CONSTRAINT {rule.name} EXPECT ({_met(rule)}){violation}"


def _met(rule: ExpectationV1) -> str:
    """True only when the row meets the rule, so a NULL result is a failure, not a lost row."""
    return f"coalesce({rule.expect}, false)"


def _passed(rules: list[ExpectationV1]) -> str:
    return " AND ".join(_met(rule) for rule in rules)


def _where_passed(rules: list[ExpectationV1]) -> str | None:
    return f"WHERE {_passed(rules)}" if rules else None


def _quarantine(rules: list[ExpectationV1], bronze: str, quarantine: str) -> str:
    """Every row silver turns away, with the name of each rule it failed as the reason."""
    reasons = [f"  IF({_met(rule)}, NULL, '{rule.name}')" for rule in rules]
    return statement(
        f"CREATE OR REFRESH STREAMING TABLE {quarantine}",
        "AS SELECT",
        "  *,",
        "  concat_ws(', ',",
        listed(reasons),
        "  ) AS _quarantine_reason",
        f"FROM STREAM({bronze})",
        f"WHERE NOT ({_passed(rules)})",
    )


def _upsert(source: Source, changes: str, silver: str) -> str:
    settings = source.silver
    return statement(
        f"CREATE FLOW upsert_{source.name} AS AUTO CDC INTO {silver}",
        f"FROM STREAM({changes})",
        f"KEYS ({', '.join(settings.keys or [])})",
        _delete_when(settings.delete_when),
        f"SEQUENCE BY {settings.sequence_by}",
        f"STORED AS SCD TYPE {settings.scd}",
    )


def _delete_when(condition: str | None) -> str | None:
    return f"APPLY AS DELETE WHEN {condition}" if condition else None
