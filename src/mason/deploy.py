"""`mason deploy`: ships one Environment and refreshes it."""

from mason import bundle, compiler, rules
from mason.databricks import Workspace
from mason.project import Project


class InvalidProject(Exception):
    pass


def deploy(project: Project, env: str, workspace: Workspace) -> None:
    if rules.check(project):
        raise InvalidProject("The project fails validation. Run `mason validate`.")
    package = compiler.write_package(project)
    workspace.deploy_bundle(package, env)
    workspace.run_job(package, env, bundle.REFRESH_JOB)
