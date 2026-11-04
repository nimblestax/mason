"""The release script, run against a throwaway repo and remote."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RELEASE = Path(__file__).parents[1] / "scripts" / "release.py"

CHANGELOG = """\
---
title: Changelog
---

## 0.1.0

- First release.
- Validates a project.

## 0.0.1

- Placeholder.
"""


# Git sets GIT_DIR and friends while running a hook, such as the pre-commit check. Left in place,
# they point every git command here at this repo rather than the throwaway one, so drop them,
# and ignore the developer's own git config too.
ENV = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")} | {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=ENV, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def release(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RELEASE), *args], cwd=repo, env=ENV, capture_output=True, text=True
    )


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    return origin


@pytest.fixture
def repo(tmp_path: Path, remote: Path) -> Path:
    """A repo on main, pushed to the remote, with version 0.1.0 and its changelog section."""
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(work, "remote", "add", "origin", str(remote))
    (work / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n')
    (work / "docs").mkdir()
    (work / "docs" / "changelog.md").write_text(CHANGELOG)
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "Start")
    git(work, "push", "-q", "-u", "origin", "main")
    return work


def test_tags_a_clean_current_main_and_pushes_the_tag(repo: Path, remote: Path) -> None:
    result = release(repo, "tag", "0.1.0")

    assert result.returncode == 0, result.stderr
    assert git(remote, "tag", "--list") == "v0.1.0"
    assert git(remote, "rev-parse", "v0.1.0^{commit}") == git(repo, "rev-parse", "HEAD")


def assert_refused(result: subprocess.CompletedProcess[str], remote: Path, reason: str) -> None:
    assert result.returncode != 0
    assert reason in result.stderr
    assert git(remote, "tag", "--list") == ""


def test_refuses_a_branch_other_than_main(repo: Path, remote: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature")

    result = release(repo, "tag", "0.1.0")

    assert_refused(result, remote, "Release from main, not feature.")


def test_refuses_a_dirty_tree(repo: Path, remote: Path) -> None:
    (repo / "notes.txt").write_text("not committed")

    result = release(repo, "tag", "0.1.0")

    assert_refused(result, remote, "Commit or stash your changes first.")


def test_refuses_a_main_behind_its_remote(tmp_path: Path, repo: Path, remote: Path) -> None:
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    git(other, "commit", "-q", "--allow-empty", "-m", "Later")
    git(other, "push", "-q", "origin", "main")

    result = release(repo, "tag", "0.1.0")

    assert_refused(result, remote, "main isn't the same as origin/main. Pull or push first.")


def commit_version(repo: Path, version: str) -> None:
    (repo / "pyproject.toml").write_text(f'[project]\nname = "demo"\nversion = "{version}"\n')
    git(repo, "commit", "-q", "-am", f"Set version {version}")
    git(repo, "push", "-q", "origin", "main")


def test_refuses_a_version_with_no_changelog_section(repo: Path, remote: Path) -> None:
    commit_version(repo, "0.2.0")

    result = release(repo, "tag", "0.2.0")

    assert_refused(result, remote, "docs/changelog.md has no section for 0.2.0.")


def test_refuses_a_version_main_does_not_carry(repo: Path, remote: Path) -> None:
    result = release(repo, "tag", "0.0.1")

    assert_refused(result, remote, "pyproject.toml says 0.1.0, not 0.0.1.")


def test_prints_only_that_versions_changelog_section(repo: Path) -> None:
    changelog = repo / "docs" / "changelog.md"
    changelog.write_text(CHANGELOG.replace("## 0.1.0", "## 0.1.0-rc.1\n\n- Candidate.\n\n## 0.1.0"))

    assert release(repo, "notes", "0.1.0").stdout == "- First release.\n- Validates a project.\n"
    assert release(repo, "notes", "0.0.1").stdout == "- Placeholder.\n"
