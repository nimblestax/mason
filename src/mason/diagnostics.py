"""One problem found in a Project, in the shape every command reports."""

from dataclasses import asdict, dataclass

RULE_FAILURE = 1
USAGE_OR_ENVIRONMENT = 2

DOCS = "https://github.com/nimblestax/mason-core/blob/main/docs/reference/json-output.md#rule-ids"

# Append only. An ID never changes meaning, and a retired rule stays here so its ID isn't reused.
RULES = {
    "MSN101": "missing-kind",
    "MSN102": "unknown-kind",
    "MSN103": "missing-version",
    "MSN104": "unknown-version",
    "MSN105": "wrong-kind",
    "MSN106": "invalid-field",
    "MSN107": "unreadable-config",
    "MSN108": "sql-without-config",
    "MSN109": "missing-sql-file",
    "MSN110": "keys-without-sequence-by",
    "MSN111": "upsert-field-without-keys",
    "MSN112": "missing-seed-file",
    "MSN113": "seed-header-mismatch",
    "MSN114": "seed-row-mismatch",
    "MSN115": "unsupported-seed-type",
    "MSN116": "invalid-expectation",
    "MSN201": "unresolved-logical-name",
    "MSN202": "duplicate-table",
    "MSN203": "unparseable-sql",
    "MSN204": "computed-table-name",
    "MSN205": "real-table-name",
    "MSN206": "file-read",
    "MSN208": "model-cycle",
    "MSN901": "usage-error",
    "MSN902": "unknown-environment",
    "MSN903": "databricks-cli-missing",
    "MSN904": "databricks-command-failed",
    "MSN905": "unexpected-error",
}


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
    return Diagnostic(rule, RULES[rule], "error", file, line, message, fix, DOCS)


class Failure(Exception):
    """Stops a command. Its diagnostics reach the user and `exit_code` ends the process."""

    def __init__(self, diagnostics: list[Diagnostic], exit_code: int = RULE_FAILURE):
        super().__init__(f"{len(diagnostics)} problem(s) found.")
        self.diagnostics = diagnostics
        self.exit_code = exit_code
