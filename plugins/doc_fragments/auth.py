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
      - Overall time budget in seconds for the module call, across every attempt and the backoff between them.
      - Each attempt gets only the time that remains as its gRPC deadline.
      - A retry that would have too little time left is not started.
      - High reasoning effort often runs for several minutes.
      - xAI recommends at least 900 seconds, and 1800 or more for long evals.
      - This replaces the SDK default of 27 minutes.
      - A shorter deadline cancels the RPC before a completion exists.
    type: float
    default: 900.0
  max_retries:
    description:
      - Extra attempts after a transient gRPC failure, at most. The first call is not counted.
      - Retried statuses are UNAVAILABLE, INTERNAL, and RST_STREAM drops.
      - The gRPC status code decides when the error has one.
      - Authentication, invalid-argument, resource or quota, and deadline errors are never retried.
      - Attempts wait a short exponential backoff with jitter, and both the wait and the retry count against O(timeout).
      - The xAI SDK itself retries UNAVAILABLE inside one attempt, under that attempt's deadline.
    type: int
    default: 2
  conversation_id:
    description:
      - Stable id for one conversation. Sent as gRPC metadata C(x-grok-conv-id) on every call made with that client.
      - Reuse it for every turn of the same conversation so prompt-cache lookups stay on one server.
      - A different conversation, such as a separate verify loop, should use its own id.
    type: str
"""
