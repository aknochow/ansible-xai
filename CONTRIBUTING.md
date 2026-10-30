# Contributing to ansible-xai

## Running Tests Locally

This repository uses `uv` for reproducible environment management with a pinned lockfile (`uv.lock`). All unit tests are deterministic and require no API keys or live credentials.

### Quick test run:
```bash
uv run pytest
```

### Syncing dependencies:
```bash
uv sync --extra dev
uv run pytest -v
```

### Running sanity tests:
Ansible sanity tests require the repository to be within an `ansible_collections/aknochow/xai` directory hierarchy:
```bash
uv run ansible-test sanity --local --python 3.13 -v
```

## Pip wheels

The git root stays a normal collection (`galaxy.yml` + `plugins/`). The PyPI name is `aknochow-xai`. `galaxy.yml` `version:` and `[project].version` must stay identical.

## Branch names

Use conventional prefixes (`feat/`, `fix/`, `docs/`, `test/`, `chore/`, `refactor/`) plus a short description. Do not use agent/product branch prefixes.

## Commit Standards

Sign every commit with `git commit -s` (DCO).
