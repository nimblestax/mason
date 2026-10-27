# Working agreement

Read before any work in this repo. These rules are non-negotiable.

## Building issues

- Build every issue test-first with `/tdd` (red → green → refactor) unless it has no testable behaviour (pure docs, config-only changes). Say so in the PR when skipping.
- Work in tracer-bullet vertical slices: each issue lands an end-to-end path, not a layer.

## Design

- Follow SOLID: small modules with one reason to change, depend on interfaces rather than concrete implementations where a seam is genuinely needed, and extend by adding code rather than editing stable code.
- Readability beats abstraction. Code is read far more than it is written, so prefer the plain, obvious version. Don't add an interface, base class, factory or layer of indirection until there is a second concrete use or a test that needs the seam. Three similar lines are better than a premature abstraction.
- A reader should be able to follow a module top to bottom without jumping through several files.

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

Any additional code-quality tooling (coverage thresholds, dependency license checks, secret scanning, dependency auditing) is welcome and, once added, equally non-negotiable.

## Task runner

- `just` is the single entry point for every routine task; CI calls the same recipes.
- Keep the root `justfile` lean: it holds only top-level recipes (`check`, `test`, `fmt`, `lint`, `typecheck`) and imports modules. Group the rest in modules under `just/` (e.g. `just/dev.just`, `just/release.just`, `just/databricks.just`) via `mod`, so each file stays short and readable.
- A recipe that grows beyond a few lines becomes a script under `scripts/`, called from the recipe.

## CI/CD

- CI is a thin wrapper over `just`: workflow steps call recipes rather than inlining shell, so local runs and CI behave the same.
- Where steps repeat across workflows, extract them into reusable components (reusable workflows via `workflow_call`, composite actions under `.github/actions/`) rather than copying them. Do this when there is real repetition, not speculatively; one workflow that reads top to bottom beats a maze of tiny pieces.
- Pin third-party actions to a version or commit SHA.
