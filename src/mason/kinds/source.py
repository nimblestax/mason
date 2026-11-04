"""A Source: a declared external dataset landed in bronze and conformed into silver."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from mason.diagnostics import Diagnostic
from mason.kinds.base import STRICT, ExactInteger, InDomain, unique
from mason.statements import statement

KIND = "source"
FOLDER = "sources"

Text = Annotated[str, Field(min_length=1)]


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
            "With no keys, it is append-only."
        ),
    )

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


def generate(source: Source, path: str, bronze: str, silver: str) -> str:
    """Bronze, then the statements that write silver, with a blank line between each."""
    return "\n\n".join([_bronze(source, path, bronze), *_silver(source, bronze, silver)]) + "\n"


def _bronze(source: Source, path: str, bronze: str) -> str:
    """Bronze keeps every row as it landed and can't be reset, so it can always be replayed."""
    return statement(
        f"CREATE OR REFRESH STREAMING TABLE {bronze}",
        "TBLPROPERTIES ('pipelines.reset.allowed' = 'false')",
        "AS SELECT *",
        f"FROM STREAM read_files('{path}', format => '{source.format}')",
    )


def _silver(source: Source, bronze: str, silver: str) -> list[str]:
    if not source.silver.keys:
        return [_append(bronze, silver)]
    return [
        statement(f"CREATE OR REFRESH STREAMING TABLE {silver}"),
        _upsert(source, bronze, silver),
    ]


def _append(bronze: str, silver: str) -> str:
    return statement(
        f"CREATE OR REFRESH STREAMING TABLE {silver}",
        "AS SELECT *",
        f"FROM STREAM({bronze})",
    )


def _upsert(source: Source, bronze: str, silver: str) -> str:
    settings = source.silver
    return statement(
        f"CREATE FLOW upsert_{source.name} AS AUTO CDC INTO {silver}",
        f"FROM STREAM({bronze})",
        f"KEYS ({', '.join(settings.keys or [])})",
        _delete_when(settings.delete_when),
        f"SEQUENCE BY {settings.sequence_by}",
        f"STORED AS SCD TYPE {settings.scd}",
    )


def _delete_when(condition: str | None) -> str | None:
    return f"APPLY AS DELETE WHEN {condition}" if condition else None
