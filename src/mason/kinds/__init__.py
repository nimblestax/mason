"""Every Kind. A new Databricks object is a new module registered in this list."""

from mason.kinds import model, platform, seed, source

KINDS = {module.KIND: module for module in (source, seed, model, platform)}
