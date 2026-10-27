# Working agreement

Read before any work in this repo. These rules are non-negotiable.

## Building issues

- Build every issue test-first with `/tdd` (red → green → refactor) unless it has no testable behaviour (pure docs, config-only changes). Say so in the PR when skipping.
- Work in tracer-bullet vertical slices: each issue lands an end-to-end path, not a layer.

## Python toolchain

| Concern | Tool |
| --- | --- |
| Environments, dependencies, running | `uv` (`uv sync`, `uv run`, `uv add`); no pip, no manual venvs |
| Formatting | `black` |
| Linting | `ruff` (lint only; `black` owns formatting, so `ruff format` is not used) |
| Type checking | `ty` |
| Tests | `pytest`, run via `uv run` |
| Gate | `pre-commit` runs all of the above; CI runs the same hooks |

Nothing merges with a failing hook. Don't add `# noqa`, `# type: ignore` or skipped tests without a comment explaining why.

Any additional code-quality tooling (coverage thresholds, dependency license checks, secret scanning) is welcome and, once added, equally non-negotiable.

## Task runner

- `just` is the single entry point for every routine task; CI calls the same recipes.
- Keep the root `justfile` lean: it holds only top-level recipes (`check`, `test`, `fmt`, `lint`, `typecheck`) and imports modules. Group the rest in modules under `just/` (e.g. `just/dev.just`, `just/release.just`, `just/databricks.just`) via `mod`.
- A recipe that grows beyond a few lines becomes a script under `scripts/`, called from the recipe.
