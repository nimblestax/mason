"""Writes `databricks.yml`: the resources, plus the placeholder values for each target."""

import yaml

from mason import names
from mason.kinds.platform import Platform
from mason.project import Project

REFRESH_JOB = "refresh"


def render(project: Project) -> str:
    platform = project.platform
    variables = list(names.settings(platform, next(iter(platform.hosts))))
    pipelines = {}
    tasks = []
    for domain in platform.domains:
        if any(source.domain == domain for source in project.sources):
            pipelines[f"{domain}_ingest"] = _pipeline(platform, domain, "ingest")
            tasks.append(_task(f"{domain}_ingest", needs=None))
        if any(model.domain == domain for model in project.models):
            pipelines[f"{domain}_gold"] = _pipeline(platform, domain, "gold")
            upstream = f"{domain}_ingest" if f"{domain}_ingest" in pipelines else None
            tasks.append(_task(f"{domain}_gold", needs=upstream))
    return yaml.safe_dump(
        {
            "bundle": {"name": platform.name},
            "variables": {name: {"description": name} for name in variables},
            "targets": {
                env: {
                    "workspace": {"host": host},
                    "variables": names.settings(platform, env),
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


def _pipeline(platform: Platform, domain: str, group: str) -> dict:
    layer = platform.source_layers[0] if group == "ingest" else platform.model_layers[-1]
    keys = names.settings(platform, next(iter(platform.hosts)))
    return {
        "name": f"{platform.name}_{domain}_{group}",
        "catalog": f"${{var.catalog_{domain}_{layer}}}",
        "schema": f"${{var.schema_{domain}_{layer}}}",
        "serverless": True,
        "channel": "CURRENT",
        "libraries": [{"glob": {"include": f"src/{domain}/{group}/**"}}],
        "configuration": {key: f"${{var.{key}}}" for key in keys},
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
