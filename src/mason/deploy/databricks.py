"""The Databricks boundary: every workspace call goes through here."""

import subprocess
import sys
from pathlib import Path
from typing import Protocol

from mason.diagnostics import USAGE_OR_ENVIRONMENT, Failure, error


class WorkspaceError(Failure):
    def __init__(self, message: str, rule: str = "MSN904", fix: str = "Read the log on stderr."):
        super().__init__([error(rule, "", message, fix)], USAGE_OR_ENVIRONMENT)


class Workspace(Protocol):
    def deploy_bundle(self, package: Path, target: str) -> None: ...

    def run_job(self, package: Path, target: str, job: str) -> None: ...


class DatabricksCli:
    def deploy_bundle(self, package: Path, target: str) -> None:
        self._bundle(package, "deploy", "--target", target)

    def run_job(self, package: Path, target: str, job: str) -> None:
        self._bundle(package, "run", "--target", target, job)

    def _bundle(self, package: Path, *arguments: str) -> None:
        command = ["databricks", "bundle", *arguments]
        try:
            # Its logs go to stderr, so stdout only ever holds what Mason prints.
            subprocess.run(command, cwd=package, check=True, stdout=sys.stderr)
        except FileNotFoundError as failure:
            raise WorkspaceError(
                "The Databricks CLI isn't installed.",
                "MSN903",
                "Install the Databricks CLI and put `databricks` on your PATH.",
            ) from failure
        except subprocess.CalledProcessError as failure:
            raise WorkspaceError(f"{' '.join(command)} failed.") from failure
