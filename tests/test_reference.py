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
from mason.kinds import KINDS, latest_schema
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


def test_every_kind_gets_a_page_that_says_it_is_generated_and_by_which_mason(tmp_path: Path):
    reference.write(tmp_path)

    for kind in KINDS:
        page = front_matter((tmp_path / f"reference/kinds/{kind}.md").read_text())
        assert page["title"]
        assert page["description"] == latest_schema(kind)[1]["description"]
        assert page["generated"] is True
        assert page["mason_version"] == version("mason-databricks")


def field_rows(page: str) -> list[list[str]]:
    """The cells of each row of a Kind page's field table, after its two header lines."""
    table = page.split("## Fields\n\n")[1].split("\n\n")[0].splitlines()[2:]
    return [[cell.strip() for cell in row.strip("|").split(" | ")] for row in table]


def test_a_kind_page_lists_every_field_with_its_type_whether_required_and_default(
    tmp_path: Path,
):
    reference.write(tmp_path)

    rows = field_rows((tmp_path / "reference/kinds/source.md").read_text())
    formats = "one of `avro`, `binaryFile`, `csv`, `json`, `orc`, `parquet`, `text`, `xml`"
    actions = "one of `warn`, `quarantine`, `fail`"
    assert [row[:4] for row in rows] == [
        ["`kind`", "`source`", "yes", ""],
        ["`version`", "`1`", "yes", ""],
        ["`path`", "string", "yes", ""],
        ["`format`", formats, "yes", ""],
        ["`silver`", "object", "no", "`{}`"],
        ["`silver.keys`", "list of string", "no", "`null`"],
        ["`silver.sequence_by`", "string", "no", "`null`"],
        ["`silver.scd`", "one of `1`, `2`", "no", "`1`"],
        ["`silver.delete_when`", "string", "no", "`null`"],
        ["`silver.expectations`", "list of object", "no", "`[]`"],
        ["`silver.expectations[].name`", "string", "yes", ""],
        ["`silver.expectations[].expect`", "string", "yes", ""],
        ["`silver.expectations[].action`", actions, "no", "`quarantine`"],
    ]


def schema_fields(schema: dict, defs: dict) -> list[tuple[str, str, str]]:
    """Each field's (name, required, description), nested objects' fields after their own."""
    fields = []
    for name, field in schema["properties"].items():
        required = "yes" if name in schema.get("required", []) else "no"
        fields.append((name, required, field["description"]))
        inner = field.get("$ref") or field.get("items", {}).get("$ref")
        if isinstance(field.get("additionalProperties"), dict):
            inner = field["additionalProperties"].get("$ref")
        if inner:
            fields += schema_fields(defs[inner.split("/")[-1]], defs)
    return fields


@pytest.mark.parametrize("kind", KINDS)
def test_a_kind_page_and_mason_schema_never_disagree(tmp_path: Path, kind: str):
    reference.write(tmp_path)
    printed = json.loads(CliRunner().invoke(app, ["schema", kind, "--json"]).stdout)
    schema = printed["result"]["json_schema"]

    rows = field_rows((tmp_path / f"reference/kinds/{kind}.md").read_text())

    listed = [(row[0].strip("`").split(".")[-1].removesuffix("[]"), row[2], row[4]) for row in rows]
    assert listed == schema_fields(schema, schema.get("$defs", {}))


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
