# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_xai_sdk(monkeypatch):
    mock_chat = MagicMock()
    mock_chat.system = MagicMock(side_effect=lambda text: ("system", text))
    mock_chat.user = MagicMock(side_effect=lambda *args: ("user", args))
    mock_chat.assistant = MagicMock(side_effect=lambda text: ("assistant", text))
    mock_chat.tool = MagicMock(side_effect=lambda **kwargs: ("tool", kwargs))
    mock_chat.image = MagicMock(side_effect=lambda url, detail="auto": ("image", url, detail))
    mock_chat.required_tool = MagicMock(side_effect=lambda name: ("required_tool", name))
    monkeypatch.setitem(sys.modules, "xai_sdk", MagicMock())
    monkeypatch.setitem(sys.modules, "xai_sdk.chat", mock_chat)
    return mock_chat


def test_ansible_messages_to_proto_roles(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        ansible_messages_to_proto,
    )

    result = ansible_messages_to_proto(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
        ]
    )

    assert result[0] == ("system", "sys")
    assert result[1] == ("user", ("hi",))
    assert result[2] == ("assistant", "yo")


def test_tools_from_openai_shape(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        tools_from_openai_shape,
    )

    tools = tools_from_openai_shape(
        [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "look up",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )

    assert tools[0][0] == "tool"
    assert tools[0][1]["name"] == "lookup"


def test_json_schema_response_format_omits_name(mock_xai_sdk, monkeypatch):
    """The live ResponseFormat proto accepts format_type and schema only."""

    class ResponseFormat:
        def __init__(self, format_type, schema):
            self.format_type = format_type
            self.schema = schema

    proto = MagicMock()
    proto.FORMAT_TYPE_JSON_SCHEMA = 3
    proto.ResponseFormat = ResponseFormat
    proto_pkg = MagicMock()
    proto_pkg.chat_pb2 = proto
    monkeypatch.setitem(sys.modules, "xai_sdk.proto", proto_pkg)
    monkeypatch.setitem(sys.modules, "xai_sdk.proto.chat_pb2", proto)

    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        response_format_from_dict,
    )

    result = response_format_from_dict(
        {
            "type": "json_schema",
            "json_schema": {
                "name": "pr_review",
                "schema": {"type": "object"},
            },
        }
    )

    assert result.format_type == 3
    assert json.loads(result.schema) == {"type": "object"}


def test_user_message_image_urls(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        ansible_messages_to_proto,
    )

    result = ansible_messages_to_proto(
        [
            {
                "role": "user",
                "content": "What is this?",
                "image_urls": ["https://example.com/a.png"],
                "image_detail": "high",
            }
        ]
    )

    assert result == [
        (
            "user",
            (
                "What is this?",
                ("image", "https://example.com/a.png", "high"),
            ),
        )
    ]
    mock_xai_sdk.image.assert_called_once_with("https://example.com/a.png", detail="high")


def test_image_urls_only_message_omits_empty_text(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        ansible_messages_to_proto,
    )

    result = ansible_messages_to_proto(
        [{"role": "user", "image_urls": ["https://example.com/a.png", "https://example.com/b.png"]}]
    )

    assert result == [
        (
            "user",
            (
                ("image", "https://example.com/a.png", "auto"),
                ("image", "https://example.com/b.png", "auto"),
            ),
        )
    ]


def test_assistant_encrypted_content_is_copied(mock_xai_sdk):
    class Message:
        def __init__(self, text):
            self.text = text
            self.encrypted_content = ""

    mock_xai_sdk.assistant = MagicMock(side_effect=Message)
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        ansible_messages_to_proto,
    )

    result = ansible_messages_to_proto(
        [{"role": "assistant", "content": "ok", "encrypted_content": "opaque-blob"}]
    )

    assert result[0].text == "ok"
    assert result[0].encrypted_content == "opaque-blob"


def test_assistant_tool_calls_and_tool_results_keep_their_ids(mock_xai_sdk, monkeypatch):
    class FunctionCall:
        def __init__(self, name="", arguments=""):
            self.name = name
            self.arguments = arguments

    class ToolCall:
        def __init__(self, id="", function=None):
            self.id = id
            self.function = function

    class Message:
        def __init__(self, text):
            self.text = text
            self.encrypted_content = ""
            self.tool_calls = []

    proto = MagicMock()
    proto.ToolCall = ToolCall
    proto.FunctionCall = FunctionCall
    proto_pkg = MagicMock()
    proto_pkg.chat_pb2 = proto
    monkeypatch.setitem(sys.modules, "xai_sdk.proto", proto_pkg)
    monkeypatch.setitem(sys.modules, "xai_sdk.proto.chat_pb2", proto)
    mock_xai_sdk.assistant = MagicMock(side_effect=Message)
    mock_xai_sdk.tool_result = MagicMock(
        side_effect=lambda result, tool_call_id=None: ("tool_result", result, tool_call_id)
    )

    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        ansible_messages_to_proto,
    )

    result = ansible_messages_to_proto(
        [
            {
                "role": "assistant",
                "content": "",
                "encrypted_content": "ENC1",
                "tool_calls": [{"id": "call_1", "name": "read_file", "args": {"path": "a.py"}}],
            },
            {"role": "tool", "content": "RESULT_A", "tool_call_id": "call_1"},
        ]
    )

    assert result[0].encrypted_content == "ENC1"
    assert result[0].tool_calls[0].id == "call_1"
    assert result[0].tool_calls[0].function.name == "read_file"
    assert json.loads(result[0].tool_calls[0].function.arguments) == {"path": "a.py"}
    assert result[1] == ("tool_result", "RESULT_A", "call_1")


def test_tool_choice_string_and_named_function(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        tool_choice_for_sdk,
    )

    assert tool_choice_for_sdk("required") == "required"
    assert tool_choice_for_sdk(None) is None
    forced = tool_choice_for_sdk({"type": "function", "function": {"name": "get_weather"}})
    assert forced == ("required_tool", "get_weather")


def test_tool_choice_rejects_unknown_string(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        tool_choice_for_sdk,
    )

    with pytest.raises(ValueError, match="tool_choice"):
        tool_choice_for_sdk("always")


def test_response_schema_is_json_not_a_pydantic_class(mock_xai_sdk, monkeypatch):
    import sys

    proto = MagicMock()
    chat_pb2 = MagicMock()
    chat_pb2.FORMAT_TYPE_JSON_SCHEMA = "json_schema"
    chat_pb2.ResponseFormat = lambda **kwargs: ("format", kwargs)
    proto.chat_pb2 = chat_pb2
    monkeypatch.setitem(sys.modules, "xai_sdk.proto", proto)
    monkeypatch.setitem(sys.modules, "xai_sdk.proto.chat_pb2", chat_pb2)

    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        response_format_from_schema,
    )

    schema = {
        "type": "object",
        "properties": {"answer": {"type": "integer"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    built = response_format_from_schema(schema)

    assert built[0] == "format"
    assert built[1]["format_type"] == "json_schema"
    assert json.loads(built[1]["schema"]) == schema
    assert "name" not in built[1]
    assert "title" not in json.loads(built[1]["schema"])


def test_response_schema_rejects_non_dict(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        response_format_from_schema,
    )

    class Answer:
        pass

    with pytest.raises(ValueError, match="JSON schema dict"):
        response_format_from_schema(Answer)


def test_image_urls_rejected_on_system_message():
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        fail_on_invalid_messages,
    )

    module = MagicMock()
    failed = fail_on_invalid_messages(
        module,
        [{"role": "system", "content": "look", "image_urls": ["https://example.com/a.png"]}],
    )

    assert failed is True
    assert "image_urls" in module.fail_json.call_args.kwargs["msg"]


def test_stop_sequences_capped_at_four():
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        fail_on_invalid_request,
    )

    module = MagicMock()
    module.params = {
        "stop_sequences": ["a", "b", "c", "d", "e"],
        "reasoning_effort": None,
        "response_schema": None,
        "response_format": None,
    }

    assert fail_on_invalid_request(module) is True
    assert "at most 4" in module.fail_json.call_args.kwargs["msg"]
