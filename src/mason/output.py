"""The `--json` envelope every command prints."""

import json
from importlib.metadata import version
from typing import Any


def envelope(command: str, ok: bool, result: dict[str, Any], diagnostics: list[dict]) -> str:
    return json.dumps(
        {
            "schema": f"mason.{command}/1",
            "mason_version": version("mason-databricks"),
            "ok": ok,
            "result": result,
            "diagnostics": diagnostics,
        },
        indent=2,
    )


def fields(kind: str, version: int, json_schema: dict[str, Any]) -> str:
    """A Kind's top-level fields, for a person reading a terminal."""
    required = json_schema["required"]
    lines = [f"{kind}, version {version}", json_schema["description"], ""]
    for name, field in json_schema["properties"].items():
        marker = " (required)" if name in required else ""
        lines.append(f"{name}{marker}: {field['description']}")
    return "\n".join(lines)
