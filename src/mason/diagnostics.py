"""One problem found in a Project, in the shape every command reports."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from mason.registry import RULES

RULE_FAILURE = 1
USAGE_OR_ENVIRONMENT = 2

# Every command shares these, so a script can read any command's exit code the same way.
EXIT_CODES = {
    0: "Clean",
    RULE_FAILURE: "Rule failures: the project needs a change",
    USAGE_OR_ENVIRONMENT: "Usage or environment error: the command line or the machine needs a"
    " change",
}

# Where Mason's docs live, so every link in a diagnostic moves together when they move.
DOCS_ROOT = "https://github.com/nimblestax/mason-core/blob/main/docs"
DOCS = f"{DOCS_ROOT}/reference/json-output.md#rule-ids"


# The descriptions are the `--json` reference, so a script reads what each field means.
@dataclass(frozen=True)
class Diagnostic:
    rule: Annotated[
        str, Field(description="The Rule's ID, such as `MSN201`. An ID never changes meaning.")
    ]
    name: Annotated[str, Field(description="The Rule's name, such as `unresolved-logical-name`.")]
    severity: Annotated[
        str, Field(description="How serious it is. Every diagnostic is an `error`.")
    ]
    file: Annotated[
        str, Field(description="The file it's in, from the project folder, or empty when none is.")
    ]
    line: Annotated[
        int | None, Field(description="The line in `file`, or `null` when it doesn't apply.")
    ]
    message: Annotated[str, Field(description="What is wrong.")]
    fix: Annotated[
        str,
        Field(description="What to change, as an instruction in words, not a patch Mason applies."),
    ]
    docs: Annotated[str, Field(description="Where the Rule is explained.")]


def error(rule: str, file: str, message: str, fix: str, line: int | None = None) -> Diagnostic:
    return Diagnostic(rule, RULES[rule].name, "error", file, line, message, fix, DOCS)


class Failure(Exception):
    """Stops a command. Its diagnostics reach the user and `exit_code` ends the process."""

    def __init__(self, diagnostics: list[Diagnostic], exit_code: int = RULE_FAILURE):
        super().__init__(f"{len(diagnostics)} problem(s) found.")
        self.diagnostics = diagnostics
        self.exit_code = exit_code
