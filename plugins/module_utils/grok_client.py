# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule, env_fallback

PROVIDER_ARGSPEC = dict(
    api_key=dict(
        type="str",
        no_log=True,
        fallback=(env_fallback, ["GROK_API_KEY", "XAI_API_KEY", "ANSIBLE_GROK_API_KEY"]),
    ),
    api_host=dict(
        type="str",
        default="api.x.ai",
        fallback=(env_fallback, ["ANSIBLE_GROK_API_HOST"]),
    ),
    timeout=dict(type="float", default=900.0),
    max_retries=dict(type="int", default=2),
)


def get_client(module: AnsibleModule):
    """Construct an xai-sdk Client for the hosted xAI API."""
    try:
        from xai_sdk import Client
    except ImportError:
        module.fail_json(msg="The xai-sdk Python package is required. Install it with: pip install xai-sdk")
        return

    api_key = module.params.get("api_key")
    if not api_key:
        module.fail_json(msg="'api_key' is required (set api_key or export GROK_API_KEY)")
        return

    timeout = module.params.get("timeout")
    if timeout is None:
        # xAI's guide asks for at least 900s. The SDK's own default is 27
        # minutes, and only applies when Client is constructed without timeout.
        timeout = 900.0

    api_host = module.params.get("api_host") or "api.x.ai"

    return Client(
        api_key=api_key,
        api_host=api_host,
        timeout=timeout,
    )
