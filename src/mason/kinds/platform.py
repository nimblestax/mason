"""The Platform Contract: `mason.platform.yaml`."""

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

FILE_NAME = "mason.platform.yaml"
KIND = "platform"

STRICT = ConfigDict(extra="forbid", frozen=True, strict=True)


class Environment(BaseModel):
    """One Environment's settings."""

    model_config = STRICT

    host: str = Field(description="Workspace URL.")


class Layers(BaseModel):
    """The Layers, in the order data flows through them."""

    model_config = STRICT

    sources: list[str] = Field(
        min_length=2, max_length=2, description="Exactly two source Layers, bronze then silver."
    )
    models: list[str] = Field(
        min_length=1, description="One or more model Layers, read left to right."
    )


class Naming(BaseModel):
    """How Logical Names map to real catalogs and schemas."""

    model_config = STRICT

    # Aliases, because `schema` is taken on every Pydantic model.
    catalog_pattern: str = Field(alias="catalog", description="The catalog pattern.")
    schema_pattern: str = Field(alias="schema", description="The schema pattern.")
    layers: Layers = Field(description="The source and model Layers.")


class PlatformV1(BaseModel):
    """The shared facts about a project's platform."""

    model_config = ConfigDict(**STRICT, title="Mason Platform Contract")

    kind: Literal["platform"] = Field(description="The Kind of this file.")
    version: Literal[1] = Field(description="The schema version of this Kind.")
    name: str = Field(min_length=1, description="The project's name.")
    environments: dict[str, Environment] = Field(
        min_length=1, description="Settings per Environment."
    )
    naming: Naming = Field(description="The catalog and schema patterns, and the Layers.")
    domains: list[str] = Field(
        json_schema_extra={"uniqueItems": True},
        description="The Domains, one folder each under `domains/`.",
    )

    @field_validator("version", mode="before")
    @classmethod
    def _version_is_an_integer(cls, value: Any) -> Any:
        # Strict mode still lets `true` through for `Literal[1]`, because `True == 1` in Python.
        if type(value) is not int:
            raise PydanticCustomError("int_type", "Input should be a valid integer")
        return value

    @field_validator("domains")
    @classmethod
    def _domains_are_unique(cls, domains: list[str]) -> list[str]:
        repeated = sorted({domain for domain in domains if domains.count(domain) > 1})
        if repeated:
            raise PydanticCustomError(
                "unique_items", "Each Domain may appear once: {repeated}", {"repeated": repeated}
            )
        return domains

    @property
    def hosts(self) -> dict[str, str]:
        return {env: settings.host for env, settings in self.environments.items()}

    @property
    def source_layers(self) -> tuple[str, str]:
        bronze, silver = self.naming.layers.sources
        return bronze, silver

    @property
    def model_layers(self) -> tuple[str, ...]:
        return tuple(self.naming.layers.models)


VERSIONS: dict[int, type[BaseModel]] = {1: PlatformV1}
Platform = PlatformV1

# `UPGRADES[n]` turns version n into version n + 1. A new version adds its model to `VERSIONS`,
# points `Platform` at it, and adds one step here.
UPGRADES: dict[int, Callable[[Any], BaseModel]] = {}
