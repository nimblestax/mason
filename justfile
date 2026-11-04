mod dev 'just/dev.just'
mod docs 'just/docs.just'

# Run every check, exactly as CI does.
check:
    uv run pre-commit run --all-files

test:
    uv run pytest

fmt:
    uv run black src tests

lint:
    uv run ruff check src tests

typecheck:
    uv run ty check src tests
