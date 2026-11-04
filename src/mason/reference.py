"""Writes the generated reference pages into the docs folder, from the code they describe."""

import sys
from importlib.metadata import version
from pathlib import Path

import yaml

from mason.registry import RULES, Example, Rule

WAY = "https://nimblestax.com/way"
LANGUAGES = {".yaml": "yaml", ".yml": "yaml", ".sql": "sql", ".csv": "csv"}


def write(docs: Path) -> None:
    rules = docs / "reference/rules"
    rules.mkdir(parents=True, exist_ok=True)
    for code, rule in RULES.items():
        (rules / f"{code.lower()}.md").write_text(_rule_page(code, rule))


def _rule_page(code: str, rule: Rule) -> str:
    sections = [
        f"## What it checks\n\n{rule.checks}\n",
        f"## Why\n\n{rule.why}\n",
        f"## Example\n\n{_example(rule.example)}",
        f"## Fix\n\n{rule.fix}\n",
    ]
    if rule.principle:
        link = f"[{rule.principle.title}]({WAY}/{rule.principle.slug})"
        sections.append(f"## Principle\n\nThis Rule enforces {link}, from the Nimblestax Way.\n")
    return _front_matter(f"{code} {rule.name}", rule.checks) + "\n" + "\n".join(sections)


def _example(example: Example) -> str:
    if example.command:
        when = f"{example.when} " if example.when else ""
        return f"{when}In a project, this fails:\n\n```console\n$ {example.command}\n```\n"
    files = [
        f"`{path}`:\n\n```{LANGUAGES[Path(path).suffix]}\n{text}```\n"
        for path, text in example.files.items()
    ]
    these = "these files" if len(files) > 1 else "this file"
    lead = f"Write {these} into the project `mason init` creates, and `mason validate` fails:"
    return f"{lead}\n\n" + "\n".join(files)


def _front_matter(title: str, description: str) -> str:
    fields = {
        "title": title,
        "description": description,
        "generated": True,
        "mason_version": version("mason-databricks"),
    }
    return f"---\n{yaml.safe_dump(fields, sort_keys=False, width=1000)}---\n"


if __name__ == "__main__":
    write(Path(sys.argv[1]))
