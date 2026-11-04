"""What every Kind's models share."""

from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, PrivateAttr
from pydantic_core import PydanticCustomError

STRICT = ConfigDict(extra="forbid", frozen=True, strict=True)

# A config file may end in either, as YAML tools accept both.
CONFIG_SUFFIXES = (".yaml", ".yml")


def config_files(folder: Path) -> list[Path]:
    """Every config file in a folder, `.yaml` or `.yml`, in name order."""
    return sorted(file for file in folder.glob("*") if file.suffix in CONFIG_SUFFIXES)


def _exact_integer(value: Any) -> Any:
    # Strict mode still lets `true` through for an integer `Literal`, because `True == 1` in Python.
    if type(value) is not int:
        raise PydanticCustomError("int_type", "Input should be a valid integer")
    return value


ExactInteger = BeforeValidator(_exact_integer)


def unique[T](values: list[T], what: str) -> list[T]:
    repeated = sorted({str(value) for value in values if values.count(value) > 1})
    if repeated:
        raise PydanticCustomError(
            "unique_items",
            "Each {what} may appear once: {repeated}",
            {"what": what, "repeated": repeated},
        )
    return values


class InDomain(BaseModel):
    """A file in a Domain's folder. Its Domain and name come from where it is, not its fields."""

    model_config = STRICT

    _config_file: Path = PrivateAttr()

    def at(self, config_file: Path) -> Self:
        """This file, knowing it was read from `config_file`, in `domains/<domain>/<folder>/`."""
        located = self.model_copy()
        located._config_file = config_file
        return located

    @property
    def config_file(self) -> Path:
        return self._config_file

    @property
    def domain(self) -> str:
        return self._config_file.parent.parent.name

    @property
    def name(self) -> str:
        return self._config_file.stem
