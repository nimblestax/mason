"""`mason deploy`: ships one Environment and refreshes it."""

from mason import bundle, compiler, rules
from mason.databricks import Workspace
from mason.diagnostics import Failure
from mason.project import Project


class InvalidProject(Failure):
    pass


def deploy(project: Project, env: str, workspace: Workspace) -> None:
    problems = rules.check(project)
    if problems:
        raise InvalidProject(problems)
    package = compiler.write_package(project)
    workspace.deploy_bundle(package, env)
    workspace.run_job(package, env, bundle.REFRESH_JOB)
