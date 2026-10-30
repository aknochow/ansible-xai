# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


class ModuleDocFragment:

    DOCUMENTATION = r"""
options:
  api_key:
    description:
      - xAI API key for api.x.ai. The same key covers Grok text models and image, video, and voice models.
      - If the value is not specified, the value of the E(GROK_API_KEY) environment variable will be used.
      - When neither is set, E(XAI_API_KEY) is accepted as an optional alias (the xAI SDK native name).
      - Optional override E(ANSIBLE_GROK_API_KEY) is also checked when resolving the key in playbooks.
    type: str
  api_host:
    description:
      - xAI API host (gRPC). Defaults to the SDK default V(api.x.ai).
      - If the value is not specified, the value of the E(ANSIBLE_GROK_API_HOST) environment variable will be used.
    type: str
    default: api.x.ai
  timeout:
    description:
      - Client deadline in seconds for each xAI gRPC call, including C(chat.stream).
      - High reasoning effort often runs for several minutes.
      - xAI recommends at least 900 seconds, and 1800 or more for long evals.
      - This replaces the SDK default of 27 minutes.
      - A shorter deadline cancels the RPC before a completion exists.
    type: float
    default: 900.0
  max_retries:
    description:
      - Reserved for future SDK retry tuning. Currently documented for parity with sibling collections.
    type: int
    default: 2
"""
