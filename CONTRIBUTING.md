# Contributing

Work on a branch and keep changes small enough to audit. A source must not be described as verified
unless repeatable checks and provenance evidence support that state.

## Development setup

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src tests
pytest
```

All four commands must pass before a pull request is merged. New functionality requires tests.
Connectors must not embed credentials, silently discard source metadata, or turn network failure into
a successful validation.

## Commits and releases

- Use clear, imperative commit subjects.
- Update `CHANGELOG.md` for user-visible changes.
- Keep the version in `src/ukei/__init__.py` and `pyproject.toml` aligned.
- Tag only a commit for which CI is green.

