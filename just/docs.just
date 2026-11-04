# Write the generated reference pages into docs/. Commit what changes.
generate:
    uv run python -m mason.reference {{justfile_directory()}}/docs
