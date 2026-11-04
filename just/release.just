# To release: merge a pull request that sets the version in pyproject.toml and adds
# its section to docs/changelog.md, then run `just release::tag <version>` on main.
# The tag starts the release workflow, which runs the rest of these recipes.

set working-directory := '..'

# Tag main as v<version> and push the tag, after checking it's ready to release.
tag version:
    uv run python scripts/release.py tag {{version}}

# Build the wheel and sdist into dist/, refusing if the tag isn't pyproject.toml's version.
build tag:
    test "{{tag}}" = "v$(uv version --short)" || { echo "{{tag}} isn't v$(uv version --short), the version in pyproject.toml." >&2; exit 1; }
    rm -rf dist
    uv build

# Publish dist/ to PyPI with Trusted Publishing, so no token is stored.
publish:
    uv publish --trusted-publishing always

# Create the GitHub Release for a tag, with the wheel and that version's changelog section.
github tag:
    uv run python scripts/release.py notes {{trim_start_match(tag, "v")}} > dist/notes.md
    gh release create {{tag}} dist/*.whl --title "Mason {{trim_start_match(tag, "v")}}" --notes-file dist/notes.md
