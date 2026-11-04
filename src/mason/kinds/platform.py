"""The Platform Contract: `mason.platform.yaml`."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mason.kinds.base import STRICT, ExactInteger, Identifier, unique

FILE_NAME = "mason.platform.yaml"
KIND = "platform"


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
    version: Annotated[Literal[1], ExactInteger] = Field(
        description="The schema version of this Kind."
    )
    name: str = Field(min_length=1, description="The project's name.")
    environments: dict[str, Environment] = Field(
        min_length=1, description="Settings per Environment."
    )
    naming: Naming = Field(description="The catalog and schema patterns, and the Layers.")
    domains: list[Identifier] = Field(
        json_schema_extra={"uniqueItems": True},
        description="The Domains, one folder each under `domains/`.",
    )

    @field_validator("domains")
    @classmethod
    def _domains_are_unique(cls, domains: list[str]) -> list[str]:
        return unique(domains, "Domain")

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
