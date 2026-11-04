import json
import re
import shlex
from importlib.metadata import version
from pathlib import Path

import pytest
from test_docs import front_matter
from typer.testing import CliRunner

from mason import reference
from mason.cli import app
from mason.registry import RULES, Example

DOCS = Path(__file__).parent.parent / "docs"


def generated_pages(docs: Path) -> dict[str, str]:
    pages = {page.relative_to(docs).as_posix(): page.read_text() for page in docs.rglob("*.md")}
    return {name: text for name, text in pages.items() if front_matter(text).get("generated")}


def test_every_rule_gets_a_page_that_says_it_is_generated_and_by_which_mason(tmp_path: Path):
    reference.write(tmp_path)

    for code in RULES:
        page = front_matter((tmp_path / f"reference/rules/{code.lower()}.md").read_text())
        assert page["title"].startswith(code)
        assert page["description"]
        assert page["generated"] is True
        assert page["mason_version"] == version("mason-databricks")


def test_the_committed_reference_is_what_mason_generates(tmp_path: Path):
    reference.write(tmp_path)

    assert generated_pages(DOCS) == generated_pages(tmp_path), "Run `just docs` and commit."


def test_every_rule_has_a_committed_page():
    missing = [
        code for code in RULES if not (DOCS / f"reference/rules/{code.lower()}.md").is_file()
    ]

    assert missing == [], "Run `just docs` and commit."


def test_a_rule_page_says_what_it_checks_why_an_example_that_fails_and_the_fix(tmp_path: Path):
    reference.write(tmp_path)

    rule = RULES["MSN201"]
    page = (tmp_path / "reference/rules/msn201.md").read_text()
    assert f"## What it checks\n\n{rule.checks}\n" in page
    assert f"## Why\n\n{rule.why}\n" in page
    for path, text in rule.example.files.items():
        assert f"`{path}`" in page
        assert f"```sql\n{text}```\n" in page
    assert f"## Fix\n\n{rule.fix}\n" in page


# An example that needs a machine in some state, such as with no Databricks CLI, says so in `when`.
RUNNABLE = {code: rule.example for code, rule in RULES.items() if not rule.example.when}


@pytest.mark.parametrize(("code", "example"), RUNNABLE.items())
def test_every_example_fails_with_its_own_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, example: Example
):
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    for path, text in example.files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    command = shlex.split(example.command or "mason validate")[1:]

    result = runner.invoke(app, [*command, "--json"])

    assert [found["rule"] for found in json.loads(result.stdout)["diagnostics"]] == [code]


def test_a_rule_page_links_the_principle_behind_it_where_there_is_one(tmp_path: Path):
    reference.write(tmp_path)

    enforced = (tmp_path / "reference/rules/msn201.md").read_text()
    assert "(https://nimblestax.com/way/every-catalog-is-one-domain)" in enforced
    assert "nimblestax.com/way" not in (tmp_path / "reference/rules/msn203.md").read_text()


def test_generated_pages_say_nothing_private(tmp_path: Path):
    reference.write(tmp_path)

    for name, text in generated_pages(tmp_path).items():
        assert not re.search(r"\bADRs?\b|nimblestax-internal|\bclients?\b", text), name
