"""A Seed: small reference data kept as a file in Git, with a declared schema."""

KIND = "seed"
SCHEMAS = {
    1: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Mason Seed",
        "description": "Small reference data kept in Git and fully replaced on each deploy.",
        "type": "object",
        "required": ["kind", "version", "file", "columns"],
        "additionalProperties": False,
        "properties": {
            "kind": {"const": "seed", "description": "The Kind of this file."},
            "version": {"const": 1, "description": "The schema version of this Kind."},
            "file": {
                "type": "string",
                "pattern": "^[^/\\\\]+\\.csv$",
                "description": "The data file, in the same folder as this file.",
            },
            "columns": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": {"type": "string"},
                "description": "Each column's name and SQL type.",
            },
        },
    }
}
