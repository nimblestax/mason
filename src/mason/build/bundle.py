"""Writes `databricks.yml`: the resources, plus the placeholder values for each target."""

import yaml

from mason import names
from mason.load.project import Project

REFRESH_JOB = "refresh"

# One retry survives a one-off blip. An error a retry can't fix, such as a bad row in append-only
# bronze, then fails in about a minute instead of waiting through the default five retries.
UPDATE_RETRIES = {"pipelines.numUpdateRetryAttempts": "1"}


def render(project: Project) -> str:
    platform = project.platform
    variables = list(names.settings(project, next(iter(platform.hosts))))
    pipelines = {}
    tasks = []
    for domain in platform.domains:
        if any(item.domain == domain for item in (*project.sources, *project.seeds)):
            pipelines[f"{domain}_ingest"] = _pipeline(project, domain, "ingest")
            tasks.append(_task(f"{domain}_ingest", needs=None))
        if any(model.domain == domain for model in project.models):
            pipelines[f"{domain}_gold"] = _pipeline(project, domain, "gold")
            upstream = f"{domain}_ingest" if f"{domain}_ingest" in pipelines else None
            tasks.append(_task(f"{domain}_gold", needs=upstream))
    return yaml.safe_dump(
        {
            "bundle": {"name": platform.name},
            # Bundle sync skips gitignored files, and `mason init` gitignores the package.
            "sync": {"include": ["src/**"]},
            "variables": {name: {"description": name} for name in variables},
            "targets": {
                env: {
                    "workspace": {"host": host},
                    "variables": names.settings(project, env),
                }
                for env, host in platform.hosts.items()
            },
            "resources": {
                "pipelines": pipelines,
                "jobs": {REFRESH_JOB: {"name": f"{platform.name}_refresh", "tasks": tasks}},
            },
        },
        sort_keys=False,
    )


def _pipeline(project: Project, domain: str, group: str) -> dict:
    platform = project.platform
    layer = platform.source_layers[0] if group == "ingest" else platform.model_layers[-1]
    keys = names.settings(project, next(iter(platform.hosts)))
    return {
        "name": f"{platform.name}_{domain}_{group}",
        "catalog": f"${{var.{names.catalog_setting(domain, layer)}}}",
        "schema": f"${{var.{names.schema_setting(domain, layer)}}}",
        "serverless": True,
        "channel": "CURRENT",
        "libraries": [{"glob": {"include": f"src/{domain}/{group}/**"}}],
        "configuration": {**{key: f"${{var.{key}}}" for key in keys}, **UPDATE_RETRIES},
    }


def _task(pipeline: str, needs: str | None) -> dict:
    task: dict = {
        "task_key": pipeline,
        "max_retries": 0,
        "pipeline_task": {"pipeline_id": f"${{resources.pipelines.{pipeline}.id}}"},
    }
    if needs:
        task["depends_on"] = [{"task_key": needs}]
    return task
