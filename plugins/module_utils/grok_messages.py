# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any

from ansible.module_utils.basic import AnsibleModule

_IMAGE_DETAILS = ("auto", "low", "high")
_TOOL_MODES = ("auto", "none", "required")
_REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh")


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content)


def _copy_encrypted(message: Any, item: dict[str, Any]) -> Any:
    encrypted = item.get("encrypted_content")
    if isinstance(encrypted, str) and encrypted:
        message.encrypted_content = encrypted
    return message


def _tool_calls_from_openai(calls: Any) -> list[Any]:
    """Build SDK tool-call protos from OpenAI-shaped ``tool_calls``."""
    from xai_sdk.proto import chat_pb2

    proto_calls = []
    for call in calls or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = call.get("name") or function.get("name") or ""
        args = call.get("args")
        if args is None:
            args = function.get("arguments")
        if not isinstance(args, str):
            args = json.dumps(args if args is not None else {})
        proto_calls.append(
            chat_pb2.ToolCall(
                id=str(call.get("id") or ""),
                function=chat_pb2.FunctionCall(name=str(name), arguments=args),
            )
        )
    return proto_calls


def ansible_messages_to_proto(messages: list[dict[str, Any]]):
    """Convert OpenAI-shaped message dicts to xai_sdk chat protobuf messages.

    A user message may include ``image_urls`` (and optional ``image_detail``).
    Those become ``xai_sdk.chat.image`` parts on the same user turn. An
    assistant message may include ``encrypted_content`` and ``tool_calls`` from
    an earlier response. A ``tool`` message is ``tool_result`` and keeps
    ``tool_call_id``. Any other role stays user text.
    """
    from xai_sdk.chat import assistant, image, system, tool_result, user

    proto_messages = []
    for item in messages:
        role = (item.get("role") or "user").lower()
        text = _message_text(item.get("content"))
        image_urls = item.get("image_urls") or []
        detail = item.get("image_detail") or "auto"

        if role == "system":
            proto_messages.append(system(text))
        elif role == "assistant":
            message = assistant(text)
            _copy_encrypted(message, item)
            if item.get("tool_calls"):
                message.tool_calls.extend(_tool_calls_from_openai(item.get("tool_calls")))
            proto_messages.append(message)
        elif role == "tool":
            tool_call_id = item.get("tool_call_id") or None
            proto_messages.append(tool_result(text, tool_call_id=tool_call_id))
        elif role == "user":
            parts: list[Any] = []
            if text or not image_urls:
                parts.append(text)
            for url in image_urls:
                parts.append(image(url, detail=detail))
            proto_messages.append(user(*parts))
        else:
            proto_messages.append(user(text))
    return proto_messages


def tools_from_openai_shape(tools: list[dict[str, Any]] | None):
    if not tools:
        return None

    from xai_sdk.chat import tool

    proto_tools = []
    for entry in tools:
        if entry.get("type") != "function":
            continue
        function = entry.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        description = function.get("description") or ""
        parameters = function.get("parameters") or {"type": "object", "properties": {}}
        proto_tools.append(tool(name=name, description=description, parameters=parameters))
    return proto_tools or None


def tool_choice_for_sdk(tool_choice: Any):
    """Map an OpenAI-style tool_choice to the value ``chat.create`` accepts.

    Strings ``auto``, ``none``, and ``required`` pass through. A dict naming a
    function becomes ``required_tool(name)``, the SDK equivalent of forcing one
    function.
    """
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        if tool_choice not in _TOOL_MODES:
            raise ValueError("tool_choice must be 'auto', 'none', 'required', or a dict naming a function")
        return tool_choice
    if isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        if not name:
            name = tool_choice.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("tool_choice dict must include function.name")
        from xai_sdk.chat import required_tool

        return required_tool(name)
    raise ValueError("tool_choice must be a string or a dict")


def response_format_from_dict(response_format: dict[str, Any] | None):
    if response_format is None:
        return None

    from xai_sdk.proto import chat_pb2

    fmt_type = response_format.get("type")
    if fmt_type == "json_object":
        return chat_pb2.ResponseFormat(format_type=chat_pb2.FORMAT_TYPE_JSON_OBJECT)
    if fmt_type == "text":
        return chat_pb2.ResponseFormat(format_type=chat_pb2.FORMAT_TYPE_TEXT)
    if fmt_type == "json_schema":
        json_schema = response_format.get("json_schema") or {}
        schema = json_schema.get("schema") or {}
        # ResponseFormat has format_type and schema only. The OpenAI-style
        # json_schema.name is not a proto field; passing it raises ValueError
        # before the request is sent.
        return chat_pb2.ResponseFormat(
            format_type=chat_pb2.FORMAT_TYPE_JSON_SCHEMA,
            schema=json.dumps(schema),
        )
    return response_format


def response_format_from_schema(schema: dict[str, Any] | None):
    """Build ``FORMAT_TYPE_JSON_SCHEMA`` the way ``Chat.parse`` does.

    ``parse`` dumps ``Model.model_json_schema()`` into the proto ``schema``
    field. Ansible cannot pass a Pydantic class, so this takes the JSON schema
    dict itself and JSON-encodes that dict. It does not construct a model.
    """
    if schema is None:
        return None
    if not isinstance(schema, dict):
        raise ValueError("response_schema must be a JSON schema dict, not a Pydantic class")
    try:
        encoded = json.dumps(schema)
    except (TypeError, ValueError) as exc:
        raise ValueError("response_schema must be a JSON-serializable dict") from exc

    from xai_sdk.proto import chat_pb2

    return chat_pb2.ResponseFormat(
        format_type=chat_pb2.FORMAT_TYPE_JSON_SCHEMA,
        schema=encoded,
    )


def fail_on_invalid_messages(module: AnsibleModule, messages: list[dict[str, Any]] | None) -> bool:
    """Validate messages. Return True when ``fail_json`` was already called."""
    if not messages:
        module.fail_json(msg="'messages' must be a non-empty list")
        return True
    for index, item in enumerate(messages):
        if not isinstance(item, dict):
            module.fail_json(msg=f"messages[{index}] must be a dict")
            return True
        if "role" not in item:
            module.fail_json(msg=f"messages[{index}] must include 'role'")
            return True
        role = str(item.get("role") or "").lower()
        image_urls = item.get("image_urls")
        image_detail = item.get("image_detail")
        if image_urls:
            if role != "user":
                module.fail_json(msg=f"messages[{index}] image_urls is only valid on role=user")
                return True
            if not isinstance(image_urls, list) or not all(isinstance(url, str) and url for url in image_urls):
                module.fail_json(msg=f"messages[{index}] image_urls must be a list of URL strings")
                return True
        if image_detail is not None:
            if not image_urls:
                module.fail_json(msg=f"messages[{index}] image_detail requires image_urls")
                return True
            if image_detail not in _IMAGE_DETAILS:
                module.fail_json(msg=f"messages[{index}] image_detail must be one of: {', '.join(_IMAGE_DETAILS)}")
                return True
    return False


def fail_on_invalid_request(module: AnsibleModule) -> bool:
    """Validate sampling and schema args. Return True when ``fail_json`` was called."""
    stop_sequences = module.params.get("stop_sequences")
    if stop_sequences is not None and len(stop_sequences) > 4:
        module.fail_json(msg="stop_sequences accepts at most 4 strings")
        return True

    reasoning_effort = module.params.get("reasoning_effort")
    if reasoning_effort is not None and reasoning_effort not in _REASONING_EFFORTS:
        module.fail_json(msg=f"reasoning_effort must be one of: {', '.join(_REASONING_EFFORTS)}")
        return True

    if module.params.get("response_schema") is not None and module.params.get("response_format") is not None:
        module.fail_json(msg="response_schema and response_format are mutually exclusive")
        return True
    return False
