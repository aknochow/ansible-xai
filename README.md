# aknochow.xai

Ansible collection that calls the **xAI API** (`api.x.ai`) via the official [`xai-sdk`](https://pypi.org/project/xai-sdk/) Python package.

Grok is the text model family on that API. The same API and key also cover image, video, and voice models. One API, not two.

## Install

```bash
ansible-galaxy collection install git+https://github.com/aknochow/ansible-xai.git
```

Or develop locally:

```bash
uv sync --extra dev
```

## Authentication

One key for `api.x.ai`. Set **`GROK_API_KEY`** in the environment. The module also accepts **`XAI_API_KEY`** (the xAI SDK name) and optional **`ANSIBLE_GROK_API_KEY`** via `env_fallback`.

Never log or commit API keys.

## Example

```yaml
- name: Ask a Grok model
  aknochow.xai.chat:
    model: grok-4.7
    max_tokens: 256
    api_key: "{{ lookup('env', 'GROK_API_KEY') }}"
    messages:
      - role: user
        content: "Hello"
  register: grok
```

## Tests

```bash
uv run pytest
```
