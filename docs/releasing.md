# Release checklist

The project uses uv for development and Hatchling to build standard wheels and source distributions. Users of a published distribution will only need pip; uv is not a runtime requirement.

## Before publishing

- Confirm the distribution name is available on PyPI. The configured name is provisional until claimed.
- Choose a license and add its file and package metadata. No license is assumed on the author's behalf.
- Add the real source, issue tracker, and documentation URLs to package metadata.
- Complete the README's applicable release milestones and document remaining alpha limitations.
- Run the checks below and test installation in a separate environment.
- Configure PyPI/TestPyPI credentials or trusted publishing outside the repository. Never commit tokens.

```shell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src/dashfsm
uv run pytest
uv build --no-sources
```

## Test publication

Use a new, unique version for each upload. TestPyPI and PyPI are separate services.

```shell
uv publish --publish-url https://test.pypi.org/legacy/
```

Install the exact wheel into a fresh environment and run the example. Inspect the wheel and source archive before a production upload. For TestPyPI installation, dependencies may need to be installed separately from PyPI.

## Production publication

After explicitly deciding to release, set the intended version in `pyproject.toml`, refresh the lockfile with `uv lock`, rerun checks, build into a clean distribution directory, and publish only that version's artifacts. Tag the matching commit and write release notes.

```shell
uv publish dist/dashfsm-<version>-py3-none-any.whl dist/dashfsm-<version>.tar.gz
```

After publication, verify `pip install dashfsm==<version>` in a clean environment and run the example journeys. Neither an account nor publication is required for local development.

Reference: [uv's official build and publication guide](https://docs.astral.sh/uv/guides/publish/).
