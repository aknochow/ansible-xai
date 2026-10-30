# ansible-xai: Project Context

## Read first

- [CONTRIBUTING.md](CONTRIBUTING.md): branch names, commits, test and lint commands
- [README.md](README.md): project overview

## What this repo is

Ansible collection that calls the xAI API (`api.x.ai`) via the official `xai-sdk` Python package. Grok is the text model family on that API. The same API and key also cover image, video, and voice models. One API, not two. Built for deterministic, structured invocation from Ansible tasks, the same shape as `aknochow.gemini` and `aknochow.openai`.

## Commands

Test and sanity commands, copied from [CONTRIBUTING.md](CONTRIBUTING.md):

### Quick test run:
```bash
uv run pytest
```

Sanity tests require the repository within `ansible_collections/aknochow/xai/` (see CONTRIBUTING.md).
