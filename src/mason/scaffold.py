"""`mason init`: writes a working project from the packaged templates."""

import json
import re
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from mason.kinds import KINDS, json_schemas

PLACEHOLDER_HOST = "https://your-workspace.cloud.databricks.com"
SCHEMA_FOLDER = Path(".mason/schemas")


def write_project(root: Path, host: str, ci: str) -> None:
    name = re.sub(r"\W+", "_", root.resolve().name).strip("_").lower()
    templates = files("mason") / "templates"
    _copy(templates / "project", root, {"host": host, "name": name})
    _copy(templates / "ci" / ci, root, {})
    _write_schemas(root)


def _write_schemas(root: Path) -> None:
    """A copy in the project, so editors check config offline and before any release."""
    folder = root / SCHEMA_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        for number, schema in json_schemas(kind).items():
            (folder / f"{kind}.v{number}.json").write_text(json.dumps(schema, indent=2) + "\n")


def _copy(template: Traversable, target: Path, values: dict[str, str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in template.iterdir():
        if entry.is_dir():
            _copy(entry, target / entry.name, values)
            continue
        text = entry.read_text()
        if entry.name == "mason.platform.yaml":
            text = text.format(**values)
        destination = ".gitignore" if entry.name == "gitignore" else entry.name
        (target / destination).write_text(
            text.replace("MASON_VERSION", version("mason-databricks"))
        )
