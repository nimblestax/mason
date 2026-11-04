"""One problem found in a Project, in the shape every command reports."""

from dataclasses import asdict, dataclass

from mason.registry import RULES

RULE_FAILURE = 1
USAGE_OR_ENVIRONMENT = 2

DOCS = "https://github.com/nimblestax/mason-core/blob/main/docs/reference/json-output.md#rule-ids"


@dataclass(frozen=True)
class Diagnostic:
    rule: str
    name: str
    severity: str
    file: str
    line: int | None
    message: str
    fix: str
    docs: str

    def as_dict(self) -> dict:
        return asdict(self)


def error(rule: str, file: str, message: str, fix: str, line: int | None = None) -> Diagnostic:
    return Diagnostic(rule, RULES[rule].name, "error", file, line, message, fix, DOCS)


class Failure(Exception):
    """Stops a command. Its diagnostics reach the user and `exit_code` ends the process."""

    def __init__(self, diagnostics: list[Diagnostic], exit_code: int = RULE_FAILURE):
        super().__init__(f"{len(diagnostics)} problem(s) found.")
        self.diagnostics = diagnostics
        self.exit_code = exit_code
