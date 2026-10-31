#!/usr/bin/python
# Copyright: (c) 2026, Adam Knochowski (@aknochow)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
---
module: chat
short_description: Send a chat completion request to the xAI API
description:
  - Calls the xAI API (C(api.x.ai)) via the official C(xai-sdk) Python package (gRPC).
  - Grok is the text model family on that API. The same API and key also cover image, video, and voice models.
  - Completions are read with C(chat.stream).
  - A unary C(chat.sample) returns nothing until the model finishes.
  - A client deadline then cancels the call with no text and no usage.
  - This is the SDK chat client, not the deprecated HTTP Chat Completions endpoint (C(POST /v1/chat/completions)).
  - Returns flattened convenience fields for use with C(register).
  - O(timeout) is one budget for the whole module call. Retries and the backoff between them spend the same budget.
version_added: "0.1.0"
author:
  - Adam Knochowski (@aknochow)
options:
  model:
    description:
      - xAI model identifier (for example V(grok-4.7)).
    type: str
    required: true
  messages:
    description:
      - List of message objects, each with C(role) (V(system), V(user), V(assistant), or V(tool)) and C(content).
      - An assistant message may set C(encrypted_content) from a previous RV(encrypted_content).
      - Pass that string back unchanged so a follow-up turn keeps the earlier reasoning.
      - An assistant message may set C(tool_calls) to the calls that turn made, each from a previous RV(tool_calls)
        (C(id), C(name), C(args)) or in OpenAI shape (C(id), C(function.name), C(function.arguments)).
      - A V(tool) message returns one result in C(content). Set C(tool_call_id) to the C(id) of the call it answers.
      - A user message may also set C(image_urls), a list of image URLs, and optional C(image_detail)
        (V(auto), V(low), or V(high)). Those are sent as image parts on that user turn.
        C(image_urls) is ignored on other roles and fails the task.
    type: list
    elements: dict
    required: true
  max_tokens:
    description:
      - Maximum number of tokens to generate. There is no default — an explicit budget must be chosen for every call.
      - This caps the visible answer. Reasoning tokens are counted separately in RV(usage).
    type: int
    required: true
  temperature:
    description:
      - Sampling temperature sent on every request. xAI recommends V(0.7). Quality usually drops when this moves far from that value.
    type: float
    default: 0.7
  top_p:
    description:
      - Nucleus sampling parameter sent on every request. xAI recommends V(0.95).
    type: float
    default: 0.95
  stop_sequences:
    description:
      - List of strings that stop generation when encountered. At most 4 sequences (xAI limit).
      - Passed to the SDK as C(stop).
    type: list
    elements: str
  response_schema:
    description:
      - 'JSON Schema dict the model must follow, for example C({"type": "object", "properties": {...}}).'
      - This is the schema object itself, not a Pydantic class and not an OpenAI C(response_format) wrapper.
      - Encoded the same way as C(xai_sdk) C(Chat.parse) (C(FORMAT_TYPE_JSON_SCHEMA) plus the schema JSON).
      - When set, the response text is parsed into the RV(structured) return value when possible.
      - Mutually exclusive with O(response_format).
    type: dict
  response_format:
    description:
      - OpenAI-shaped structured-output configuration (V(text), V(json_object), or V(json_schema) with a nested schema).
      - Prefer O(response_schema) when the playbook already has a bare JSON Schema dict.
      - When set to a JSON schema or JSON object shape, the response text is parsed into RV(structured) when possible.
      - Mutually exclusive with O(response_schema).
    type: dict
  tools:
    description:
      - List of tool definitions in OpenAI function-calling format.
      - Each entry is C(type) V(function) plus C(function.name), C(function.description), and C(function.parameters).
      - Converted to C(xai_sdk.chat.tool) and passed to C(chat.create). The module does not execute tools.
    type: list
    elements: dict
  tool_choice:
    description:
      - Controls tool-use behavior.
      - A string V(auto), V(none), or V(required), or a dict that names one function.
      - 'Example: C({"type": "function", "function": {"name": "get_weather"}}).'
      - A dict is sent as the SDK's required-tool choice for that function name.
    type: raw
  parallel_tool_calls:
    description:
      - Whether the model may return more than one tool call in a single response.
      - When omitted, the server default applies (true). Set V(false) to allow at most one.
    type: bool
  reasoning_effort:
    description:
      - Reasoning effort passed to C(chat.create). Choices are V(none), V(low), V(medium), V(high), or V(xhigh).
      - Set this on every call whose result must not depend on the model's server default. V(grok-4.7) defaults to V(high). V(grok-4.3) defaults to V(low).
      - When omitted, this module sends nothing and the server default applies.
      - V(none) is model-dependent. grok-4.5 and newer still reason and cannot turn reasoning off.
      - The trace is returned in RV(reasoning) and the token count in RV(usage.reasoning_tokens).
    type: str
    choices: ["none", "low", "medium", "high", "xhigh"]
  use_encrypted_content:
    description:
      - Ask the API for the encrypted reasoning item and return it as RV(encrypted_content).
      - A later task that continues the conversation should copy that string onto the assistant message. Dropping it makes the next turn reason from scratch.
      - One-shot tasks can leave the default. The string is opaque; do not edit it.
    type: bool
    default: true
extends_documentation_fragment:
  - aknochow.xai.auth
requirements:
  - "xai-sdk (PyPI package name: xai-sdk)"
"""

EXAMPLES = r"""
- name: Basic chat completion
  aknochow.xai.chat:
    model: grok-4.7
    max_tokens: 512
    reasoning_effort: high
    messages:
      - role: user
        content: "Summarize this changelog in one sentence: {{ changelog }}"
  register: result

- name: Structured extraction with a JSON schema dict
  aknochow.xai.chat:
    model: grok-4.7
    max_tokens: 1024
    messages:
      - role: user
        content: "Extract the name and severity from this bug report: {{ bug_text }}"
    response_schema:
      type: object
      properties:
        name: {type: string}
        severity: {type: string, enum: [low, medium, high, critical]}
      required: [name, severity]
      additionalProperties: false
  register: result

- name: Force a single tool call
  aknochow.xai.chat:
    model: grok-4.7
    max_tokens: 256
    temperature: 0.7
    top_p: 0.95
    parallel_tool_calls: false
    messages:
      - role: user
        content: "What's the weather in Boston?"
    tools:
      - type: function
        function:
          name: get_weather
          description: Get the current weather for a location
          parameters:
            type: object
            properties:
              city: {type: string}
            required: [city]
    tool_choice:
      type: function
      function:
        name: get_weather
  register: result

- name: Ask about an image
  aknochow.xai.chat:
    model: grok-4.7
    max_tokens: 256
    reasoning_effort: low
    messages:
      - role: user
        content: "What is in this picture?"
        image_urls:
          - https://example.com/diagram.png
        image_detail: high
  register: result
"""

RETURN = r"""
response:
  description: Raw response metadata from the xAI SDK (protobuf serialized to JSON-friendly dict).
  type: dict
  returned: always
text:
  description: The final answer text.
  type: str
  returned: always
tool_calls:
  description: List of tool calls the model made, each with C(id), C(name), and C(args).
  type: list
  returned: always
reasoning:
  description: The model's reasoning trace from C(reasoning_content), when the response includes one.
  type: str
  returned: when a reasoning trace was generated
encrypted_content:
  description:
    - Opaque encrypted reasoning from the response. Pass it back unchanged as C(encrypted_content) on the assistant message of the next task.
    - Present when O(use_encrypted_content) is true and the API returned a reasoning item.
  type: str
  returned: when encrypted reasoning was returned
structured:
  description: Parsed JSON object when O(response_schema) or O(response_format) requested structured output.
  type: dict
  returned: when structured output was requested and parsing succeeds
finish_reason:
  description:
    - Why generation stopped, for example V(REASON_STOP) or V(REASON_TOOL_CALLS).
    - V(REASON_MAX_LEN) means O(max_tokens) cut the answer short. The task still succeeds, so check for it when that matters.
  type: str
  returned: always
partial_text:
  description:
    - Text received before the call failed, or an empty string when none arrived.
    - Comes from the most recent attempt that received any text.
  type: str
  returned: on failure after the request was started
attempts:
  description:
    - One entry per attempt made, oldest first. The last entry is the attempt that decided the result.
    - Use this to account for usage that RV(usage) does not cover, such as an attempt whose stream dropped.
  type: list
  elements: dict
  returned: always once the request was started, on success and on failure
  contains:
    usage:
      description:
        - Usage received on this attempt, in the same shape as RV(usage).
        - V(null) when the attempt received none. A dropped stream often reports none, and its cost is then unknown, not zero.
      type: dict
    error:
      description:
        - Failure text for this attempt with the API key redacted. V(null) when the attempt succeeded with no error.
        - On a successful result this can hold the error that ended the stream after the response had already finished.
      type: str
usage:
  description: Token usage for the final response. Earlier attempts are reported in RV(attempts).
  type: dict
  returned: on success
  contains:
    prompt_tokens:
      description: Number of input tokens billed for this request.
      type: int
    completion_tokens:
      description: Number of output tokens generated.
      type: int
    total_tokens:
      description: Total tokens billed for this request.
      type: int
    cached_tokens:
      description: Prompt tokens served from the provider cache, when reported.
      type: int
    reasoning_tokens:
      description: Reasoning tokens billed for this request. Present even when zero.
      type: int
    cost_in_usd_ticks:
      description: Provider-reported cost of this request in USD ticks, or zero when not reported.
      type: int
"""

import json
import random
import time

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import (
    DEFAULT_TIMEOUT_SECONDS,
    PROVIDER_ARGSPEC,
    get_client,
)
from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
    ansible_messages_to_proto,
    fail_on_invalid_messages,
    fail_on_invalid_request,
    response_format_from_dict,
    response_format_from_schema,
    tool_choice_for_sdk,
    tools_from_openai_shape,
)

# A retry needs this much of the budget left once its backoff has been spent.
_MIN_ATTEMPT_SECONDS = 10.0
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 8.0

_TRANSIENT_STATUSES = frozenset({"INTERNAL", "UNAVAILABLE"})
# gRPC reports some RST_STREAM drops under these statuses instead of INTERNAL.
_RST_STREAM_STATUSES = frozenset({"UNKNOWN", "CANCELLED"})
_NO_FINISH_REASON = "REASON_INVALID"
_NEVER_RETRIED_TOKENS = (
    "DEADLINE_EXCEEDED",
    "UNAUTHENTICATED",
    "PERMISSION_DENIED",
    "INVALID_ARGUMENT",
    "RESOURCE_EXHAUSTED",
)


class _StreamUnfinished(Exception):
    """The stream closed cleanly before the response had a finish reason."""


def flatten_tool_calls(tool_calls):
    flattened = []
    for tc in tool_calls or []:
        raw_args = getattr(getattr(tc, "function", None), "arguments", None)
        if raw_args is None:
            raw_args = ""
        try:
            args = json.loads(raw_args) if raw_args else {}
        except (json.JSONDecodeError, ValueError, TypeError):
            args = raw_args
        name = getattr(getattr(tc, "function", None), "name", None) or ""
        flattened.append(dict(id=getattr(tc, "id", None), name=name, args=args))
    return flattened


def _usage_int(usage, name):
    value = getattr(usage, name, 0)
    return value if isinstance(value, int) else 0


def flatten_usage(usage):
    if usage is None:
        return dict(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cached_tokens=0,
            reasoning_tokens=0,
            cost_in_usd_ticks=0,
        )
    return dict(
        prompt_tokens=_usage_int(usage, "prompt_tokens"),
        completion_tokens=_usage_int(usage, "completion_tokens"),
        total_tokens=_usage_int(usage, "total_tokens"),
        cached_tokens=_usage_int(usage, "cached_prompt_text_tokens"),
        reasoning_tokens=_usage_int(usage, "reasoning_tokens"),
        cost_in_usd_ticks=_usage_int(usage, "cost_in_usd_ticks"),
    )


def parse_structured_text(text):
    """Return the JSON value in text, or None when text is not one value.

    grok-4.7 has returned the same object twice in one response, so exact
    repeats count as one value. Differing values stay unparsed, because
    choosing one would be a guess.
    """
    decoder = json.JSONDecoder()
    remaining = text.strip()
    try:
        value, end = decoder.raw_decode(remaining)
        remaining = remaining[end:].lstrip()
        while remaining:
            repeat, end = decoder.raw_decode(remaining)
            if repeat != value:
                return None
            remaining = remaining[end:].lstrip()
    except ValueError:
        return None
    return value


def flatten_response(response, parse_structured=False):
    # Imported here so ansible-test compile/import can load the module
    # without protobuf, which arrives only with xai-sdk at runtime.
    from google.protobuf.json_format import MessageToDict

    text = response.content or ""
    reasoning = response.reasoning_content or None
    tool_calls = flatten_tool_calls(response.tool_calls)

    structured = None
    if parse_structured and text:
        structured = parse_structured_text(text)

    raw = MessageToDict(response.proto, preserving_proto_field_name=True)

    result = dict(
        response=raw,
        text=text,
        tool_calls=tool_calls,
        finish_reason=response.finish_reason,
        usage=flatten_usage(response.usage),
    )
    if reasoning:
        result["reasoning"] = reasoning
    encrypted = getattr(response, "encrypted_content", None)
    if isinstance(encrypted, str) and encrypted:
        result["encrypted_content"] = encrypted
    if structured is not None:
        result["structured"] = structured
    return result


def _or_default(value, default):
    if value is None:
        return default
    return value


def _status_name(exc: BaseException):
    """Return the gRPC status name carried by an exception, or None."""
    code = getattr(exc, "code", None)
    if not callable(code):
        return None
    try:
        name = getattr(code(), "name", None)
    except Exception:
        return None
    return name if isinstance(name, str) else None


def _is_transient(exc: BaseException) -> bool:
    """True for a dropped stream that is worth another attempt.

    The status code decides when the exception has one. Text is only read for
    an RST_STREAM drop under a generic status and for exceptions with no code.
    """
    if isinstance(exc, _StreamUnfinished):
        return True
    text = str(exc)
    status = _status_name(exc)
    if status is not None:
        if status in _TRANSIENT_STATUSES:
            return True
        return status in _RST_STREAM_STATUSES and "RST_STREAM" in text
    if any(token in text for token in _NEVER_RETRIED_TOKENS):
        return False
    return any(token in text for token in ("UNAVAILABLE", "RST_STREAM", "StatusCode.INTERNAL"))


def _deadline_exceeded(exc: BaseException) -> bool:
    status = _status_name(exc)
    if status is not None:
        return status == "DEADLINE_EXCEEDED"
    return "DEADLINE_EXCEEDED" in str(exc)


def _backoff_seconds(retry_index: int) -> float:
    """Exponential backoff with jitter, between half of the step and all of it."""
    step = min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * (2**retry_index))
    return random.uniform(step / 2, step)


def _received_usage(response):
    """Flatten usage only if some arrived, so missing usage is not reported as zeros."""
    if response is None:
        return None
    usage = flatten_usage(getattr(response, "usage", None))
    return usage if any(usage.values()) else None


def _is_finished(response):
    """True once the response carries a real finish reason, REASON_MAX_LEN included."""
    try:
        reason = getattr(response, "finish_reason", None)
    except ValueError:
        # The SDK cannot name an enum value it does not know.
        return False
    return isinstance(reason, str) and bool(reason) and reason != _NO_FINISH_REASON


def _received_text(response, fallback):
    try:
        return getattr(response, "content", None) or fallback
    except Exception:
        return fallback


def _redact(text, api_key):
    if api_key and api_key in text:
        return text.replace(api_key, "<api_key>")
    return text


def _close_client(client):
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            # Nothing is left to do with a client that will not close, and this
            # runs after the attempt, so it must not replace the attempt's result.
            pass


def _fail(module, exc, budget, partial, attempts):
    """Report a final failure. exc is None when the budget ended with no error."""
    if exc is None or _deadline_exceeded(exc):
        msg = (
            f"The xAI stream exceeded the client timeout of {budget} seconds "
            "before the response finished."
        )
        if partial:
            msg = f"{msg} Partial text ({len(partial)} characters) was received."
    else:
        msg = _redact(str(exc), module.params.get("api_key"))
    module.fail_json(msg=msg, partial_text=partial, attempts=attempts)


def main():
    started = time.monotonic()
    argument_spec = dict(
        model=dict(type="str", required=True),
        messages=dict(type="list", elements="dict", required=True),
        max_tokens=dict(type="int", required=True, no_log=False),
        stop_sequences=dict(type="list", elements="str"),
        response_schema=dict(type="dict"),
        response_format=dict(type="dict"),
        tools=dict(type="list", elements="dict"),
        tool_choice=dict(type="raw"),
        parallel_tool_calls=dict(type="bool"),
        reasoning_effort=dict(
            type="str",
            choices=["none", "low", "medium", "high", "xhigh"],
        ),
        temperature=dict(type="float", default=0.7),
        top_p=dict(type="float", default=0.95),
        use_encrypted_content=dict(type="bool", default=True),
    )
    argument_spec.update(PROVIDER_ARGSPEC)

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if fail_on_invalid_messages(module, module.params["messages"]):
        return
    if fail_on_invalid_request(module):
        return

    # This client only validates the key and SDK. The xAI SDK fixes a client's
    # deadline when it is built and applies it to every RPC, so each attempt
    # below builds its own client with the time that is left.
    client = get_client(module)
    if client is None:
        return
    _close_client(client)

    api_key = module.params.get("api_key")
    try:
        messages = ansible_messages_to_proto(module.params["messages"])
        tools = tools_from_openai_shape(module.params.get("tools"))
    except Exception as exc:
        reason = _redact(f"{type(exc).__name__}: {exc}", api_key)
        module.fail_json(msg=f"Could not convert messages or tools to an xAI request. {reason}")
        return

    schema = module.params.get("response_schema")
    response_format_param = module.params.get("response_format")
    try:
        if schema is not None:
            response_format = response_format_from_schema(schema)
        else:
            response_format = response_format_from_dict(response_format_param)
        tool_choice = tool_choice_for_sdk(module.params.get("tool_choice"))
    except ValueError as exc:
        module.fail_json(msg=str(exc))
        return

    # Sampling is sent on every request. xAI recommends 0.7 / 0.95.
    # reasoning_effort stays off the request when unset so a model's own
    # default applies (high on grok-4.7, low on grok-4.3).
    create_kwargs = dict(
        model=module.params["model"],
        messages=messages,
        max_tokens=module.params["max_tokens"],
        temperature=_or_default(module.params.get("temperature"), 0.7),
        top_p=_or_default(module.params.get("top_p"), 0.95),
        use_encrypted_content=_or_default(module.params.get("use_encrypted_content"), True),
        # Each request already carries the full history. Do not keep a server copy.
        store_messages=False,
    )

    stop_sequences = module.params.get("stop_sequences")
    if stop_sequences is not None:
        create_kwargs["stop"] = stop_sequences

    if tools is not None:
        create_kwargs["tools"] = tools

    if tool_choice is not None:
        create_kwargs["tool_choice"] = tool_choice

    parallel_tool_calls = module.params.get("parallel_tool_calls")
    if parallel_tool_calls is not None:
        create_kwargs["parallel_tool_calls"] = parallel_tool_calls

    reasoning_effort = module.params.get("reasoning_effort")
    if reasoning_effort is not None:
        create_kwargs["reasoning_effort"] = reasoning_effort

    if response_format is not None:
        create_kwargs["response_format"] = response_format

    parse_structured = schema is not None or bool(response_format_param)
    max_retries = module.params.get("max_retries")
    max_attempts = max(0, max_retries if isinstance(max_retries, int) else 0) + 1
    budget = _or_default(module.params.get("timeout"), DEFAULT_TIMEOUT_SECONDS)
    deadline = started + budget

    attempts = []
    partial = ""
    last_error = None
    response = None
    for attempt in range(max_attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Never hand the SDK a zero: it reads that as its 27 minute default.
            _fail(module, last_error, budget, partial, attempts)
            return

        response = None
        attempt_client = None
        try:
            attempt_client = get_client(module, timeout=remaining)
            if attempt_client is None:
                return
            chat = attempt_client.chat.create(**create_kwargs)
            for response, _chunk in chat.stream():
                pass
            if response is None:
                msg = "The xAI stream ended before any response chunk arrived."
                attempts.append(dict(usage=None, error=msg))
                module.fail_json(msg=msg, partial_text=partial, attempts=attempts)
                return
            if not _is_finished(response):
                raise _StreamUnfinished("The xAI stream ended without a finish reason, so the response may be truncated.")
            attempts.append(dict(usage=_received_usage(response), error=None))
            break
        except Exception as exc:
            last_error = exc
            attempts.append(dict(usage=_received_usage(response), error=_redact(str(exc), api_key)))
            if _is_finished(response):
                # The answer was complete before the stream failed. A retry would pay for it again.
                break
            partial = _received_text(response, partial)
            if attempt + 1 < max_attempts and _is_transient(exc):
                delay = _backoff_seconds(attempt)
                if deadline - time.monotonic() - delay >= _MIN_ATTEMPT_SECONDS:
                    time.sleep(delay)
                    continue
            _fail(module, exc, budget, partial, attempts)
            return
        finally:
            _close_client(attempt_client)

    try:
        result = flatten_response(response, parse_structured=parse_structured)
    except Exception as exc:
        attempts[-1]["error"] = _redact(str(exc), api_key)
        _fail(module, exc, budget, _received_text(response, partial), attempts)
        return
    module.exit_json(changed=False, attempts=attempts, **result)


if __name__ == "__main__":
    main()
