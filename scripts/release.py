"""Cut a release of Mason, and read its notes from the changelog.

    release.py tag <version>    tag main as v<version> and push the tag
    release.py notes <version>  print that version's changelog section

Pushing the tag starts the release workflow, which publishes to PyPI.
"""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

CHANGELOG = "docs/changelog.md"


class Refused(Exception):
    pass


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return done.stdout.strip()


def notes(version: str) -> str:
    """The changelog section for `version`, without its heading."""
    text = Path(CHANGELOG).read_text()
    heading = rf"^## {re.escape(version)}(?:[ \t].*)?$"
    found = re.search(rf"{heading}(.*?)(?=^## |\Z)", text, re.M | re.S)
    if found is None:
        raise Refused(f"{CHANGELOG} has no section for {version}.")
    return found.group(1).strip()


def tag(version: str) -> None:
    branch = git("branch", "--show-current")
    if branch != "main":
        raise Refused(f"Release from main, not {branch}.")
    if git("status", "--porcelain"):
        raise Refused("Commit or stash your changes first.")
    git("fetch", "-q", "origin", "main")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        raise Refused("main isn't the same as origin/main. Pull or push first.")
    carried = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    if carried != version:
        raise Refused(f"pyproject.toml says {carried}, not {version}.")
    notes(version)
    git("tag", "-a", f"v{version}", "-m", f"Mason {version}")
    git("push", "-q", "origin", f"v{version}")
    print(f"Pushed v{version}. The release workflow takes it from here.")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("tag", "notes"):
        print(__doc__, file=sys.stderr)
        return 2
    command, version = argv
    try:
        if command == "tag":
            tag(version)
        else:
            print(notes(version))
    except Refused as refusal:
        print(refusal, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
