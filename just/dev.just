# Install dependencies and the git hook.
setup:
    uv sync
    uv run pre-commit install
