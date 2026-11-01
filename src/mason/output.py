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
