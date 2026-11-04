"""Turns a Project into generated code: one file per table group, same in every Environment."""

import shutil
from pathlib import Path

from mason import names, sql
from mason.build import bundle
from mason.kinds import model, seed, source
from mason.load.project import Project
from mason.names import LogicalName

BUILD_FOLDER = "build"


def generated_files(project: Project) -> dict[Path, str]:
    """Generated code by path relative to the package, using placeholders."""
    files: dict[Path, str] = {}
    bronze_layer, silver_layer = project.platform.source_layers
    gold_layer = project.platform.model_layers[-1]
    for item in project.sources:
        bronze = names.placeholders(LogicalName(item.domain, bronze_layer, item.name))
        silver = names.placeholders(LogicalName(item.domain, silver_layer, item.name))
        quarantine = names.placeholders(LogicalName(item.domain, silver_layer, item.quarantine))
        path = Path("src") / item.domain / "ingest" / f"{item.name}.sql"
        files[path] = source.generate(
            item, names.path_placeholder(item), bronze, silver, quarantine
        )
    for item in project.seeds:
        target = names.placeholders(LogicalName(item.domain, silver_layer, item.name))
        files[Path("src") / item.domain / "ingest" / f"{item.name}.sql"] = seed.generate(
            item, target
        )
    for item in project.models:
        target = names.placeholders(LogicalName(item.domain, gold_layer, item.name))
        path = Path("src") / item.domain / "gold" / f"{item.name}.sql"
        files[path] = model.generate(item, target, sql.rewrite(item.query, names.placeholders))
    return files


def write_package(project: Project) -> Path:
    package = project.root / BUILD_FOLDER
    shutil.rmtree(package, ignore_errors=True)
    package.mkdir()
    for relative, content in generated_files(project).items():
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (package / "databricks.yml").write_text(bundle.render(project))
    return package


def print_for(project: Project, env: str) -> str:
    """Every generated file as runnable SQL for one Environment."""
    code = "\n".join(generated_files(project).values())
    return names.resolve(code, project, env)
