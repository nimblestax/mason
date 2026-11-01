"""The Databricks boundary: every workspace call goes through here."""

import subprocess
from pathlib import Path
from typing import Protocol


class WorkspaceError(Exception):
    pass


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
            subprocess.run(command, cwd=package, check=True)
        except FileNotFoundError as error:
            raise WorkspaceError("The Databricks CLI isn't installed.") from error
        except subprocess.CalledProcessError as error:
            raise WorkspaceError(f"{' '.join(command)} failed.") from error
