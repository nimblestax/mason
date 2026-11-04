"""The Databricks boundary: every workspace call goes through here."""

import json
import subprocess
import sys
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from mason.diagnostics import USAGE_OR_ENVIRONMENT, Failure, error

# How many of the CLI's last lines a failure keeps, since the CLI's own output goes to stderr.
KEPT_LINES = 10

# The workspace's clock and this machine's can differ a little, so errors are read from a bit
# before the refresh started. A failed deploy takes longer than this, so no older error shows up.
CLOCK_SKEW = timedelta(minutes=1)


class WorkspaceError(Failure):
    def __init__(self, message: str, rule: str = "MSN904", fix: str = "Read the log on stderr."):
        super().__init__([error(rule, "", message, fix)], USAGE_OR_ENVIRONMENT)


class Workspace(Protocol):
    def deploy_bundle(self, package: Path, target: str) -> None: ...

    def run_job(self, package: Path, target: str, job: str) -> None: ...

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        """The errors of each pipeline's newest update that failed since `since`."""
        ...


class DatabricksCli:
    def deploy_bundle(self, package: Path, target: str) -> None:
        self._stream(package, "bundle", "deploy", "--target", target)

    def run_job(self, package: Path, target: str, job: str) -> None:
        self._stream(package, "bundle", "run", "--target", target, job)

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        summary = self._json(package, "bundle", "summary", "--target", target, "-o", "json")
        pipelines = summary.get("resources", {}).get("pipelines", {}).values()
        start = (since - CLOCK_SKEW).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        errors = []
        for pipeline in pipelines:
            if "id" not in pipeline:
                continue  # Never deployed, so it has no log.
            events = self._json(
                package,
                *("pipelines", "list-pipeline-events", pipeline["id"], "--target", target),
                *("-o", "json", "--filter", f"level='ERROR' AND timestamp >= '{start}'"),
            )
            errors.extend(failed_update_errors(events))
        return errors

    def _stream(self, package: Path, *arguments: str) -> None:
        command = ["databricks", *arguments]
        last_lines: deque[str] = deque(maxlen=KEPT_LINES)
        # Its output goes to stderr, so stdout only ever holds what Mason prints.
        with _start(command, package, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as cli:
            for line in cli.stdout or []:
                sys.stderr.write(line)
                last_lines.append(line.rstrip())
        if cli.returncode:
            shown = "\n".join(last_lines)
            raise WorkspaceError(f"{' '.join(command)} failed. Its last lines:\n{shown}")

    def _json(self, package: Path, *arguments: str) -> Any:
        command = ["databricks", *arguments]
        with _start(command, package, stdout=subprocess.PIPE, stderr=sys.stderr) as cli:
            printed = cli.stdout.read() if cli.stdout else ""
        if cli.returncode:
            raise WorkspaceError(f"{' '.join(command)} failed.")
        try:
            return json.loads(printed)
        except json.JSONDecodeError as failure:
            raise WorkspaceError(f"{' '.join(command)} didn't print JSON.") from failure


def _start(command: list[str], package: Path, **streams: Any) -> subprocess.Popen[str]:
    try:
        return subprocess.Popen(command, cwd=package, text=True, **streams)
    except FileNotFoundError as failure:
        raise WorkspaceError(
            "The Databricks CLI isn't installed.",
            "MSN903",
            "Install the Databricks CLI and put `databricks` on your PATH.",
        ) from failure


def failed_update_errors(events: list[dict]) -> list[str]:
    """The first line of each error in the newest update, from a pipeline's ERROR events.

    Events come newest first. A failed flow logs its own error and then the update logs a summary,
    so the flows' errors are kept, and the update's own only when no flow failed.
    """
    if not events:
        return []
    newest = _origin(events[0]).get("update_id")
    in_update = [found for found in reversed(events) if _origin(found).get("update_id") == newest]
    from_flows = [found for found in in_update if _origin(found).get("flow_name")]
    errors = []
    for found in from_flows or in_update:
        message = _error_message(found)
        if message and message not in errors:
            errors.append(message)
    return errors


def _origin(found: dict) -> dict:
    return found.get("origin", {})


def _error_message(found: dict) -> str:
    exceptions = found.get("error", {}).get("exceptions") or [{}]
    message = exceptions[0].get("message") or found.get("message") or ""
    return message.splitlines()[0] if message else ""
