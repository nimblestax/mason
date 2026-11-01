"""One problem found in a Project, in the shape every command reports."""

from dataclasses import asdict, dataclass


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
