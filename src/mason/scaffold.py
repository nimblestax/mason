"""`mason init`: writes a working project from the packaged templates."""

import re
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

PLACEHOLDER_HOST = "https://your-workspace.cloud.databricks.com"


def write_project(root: Path, host: str, ci: str) -> None:
    name = re.sub(r"\W+", "_", root.resolve().name).strip("_").lower()
    templates = files("mason") / "templates"
    _copy(templates / "project", root, {"host": host, "name": name})
    _copy(templates / "ci" / ci, root, {})


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
