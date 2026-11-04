"""`mason deploy`: ships one Environment and refreshes it."""

from datetime import datetime

from mason.build import bundle, compiler
from mason.check import rules
from mason.deploy.databricks import Workspace, WorkspaceError
from mason.diagnostics import USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error
from mason.load.project import Project

RECOVERY_GUIDE = "docs/guides/recover-from-a-failed-refresh.md"


class InvalidProject(Failure):
    pass


def deploy(project: Project, env: str, workspace: Workspace) -> None:
    problems = rules.check(project)
    if problems:
        raise InvalidProject(problems)
    package = compiler.write_package(project)
    workspace.deploy_bundle(package, env)
    started = datetime.now().astimezone()
    try:
        workspace.run_job(package, env, bundle.REFRESH_JOB)
    except WorkspaceError as failure:
        try:
            errors = workspace.pipeline_errors(package, env, started)
        except WorkspaceError:
            errors = []
        if not errors:
            raise failure
        found = [refresh_failure(message) for message in errors]
        raise Failure(found, USAGE_OR_ENVIRONMENT) from failure


def refresh_failure(message: str) -> Diagnostic:
    """A pipeline's error during the refresh, with how to recover from it."""
    if "UNRESOLVED_COLUMN" in message:
        fix = (
            "Correct the column's name. If an Expectation names a column bronze doesn't have"
            " yet, deploy without the rule so bronze picks up the column, then add the rule back."
            f" See {RECOVERY_GUIDE}."
        )
        return error("MSN906", "", message, fix)
    if "EXPECTATION_VIOLATION" in message:
        fix = (
            "The row that broke the rule stays in bronze, so every refresh fails on it again."
            " Correct the rule, or change its `action` to `quarantine` or `warn`, then deploy."
            f" See {RECOVERY_GUIDE}."
        )
        return error("MSN907", "", message, fix)
    fix = "Fix the cause, then deploy again. The pipeline's event log in the workspace has more."
    return error("MSN908", "", message, fix)
