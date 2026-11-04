"""The `--json` envelope every command prints."""

import json
from importlib.metadata import version
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mason.diagnostics import Diagnostic


class Envelope(BaseModel):
    """The fields of the envelope, in the order they are printed."""

    model_config = ConfigDict(validate_by_name=True)

    schema_: str = Field(
        alias="schema",
        description="The command and the version of its result, such as `mason.validate/1`. A"
        " usage error that names no command uses `mason.usage/1`.",
    )
    mason_version: str = Field(description="The installed Mason.")
    ok: bool = Field(description="Whether the command succeeded.")
    result: dict[str, Any] = Field(
        description="The command's own output, which its page describes. It is `{}` when the"
        " command fails."
    )
    diagnostics: list[Diagnostic] = Field(description="Every problem found.")


def envelope(command: str, ok: bool, result: dict[str, Any], diagnostics: list[Diagnostic]) -> str:
    printed = Envelope(
        schema_=f"mason.{command}/1",
        mason_version=version("mason-databricks"),
        ok=ok,
        result=result,
        diagnostics=diagnostics,
    )
    return json.dumps(printed.model_dump(mode="json", by_alias=True), indent=2)


def fields(kind: str, version: int, json_schema: dict[str, Any]) -> str:
    """A Kind's top-level fields, for a person reading a terminal."""
    required = json_schema["required"]
    lines = [f"{kind}, version {version}", json_schema["description"], ""]
    for name, field in json_schema["properties"].items():
        marker = " (required)" if name in required else ""
        lines.append(f"{name}{marker}: {field['description']}")
    return "\n".join(lines)
