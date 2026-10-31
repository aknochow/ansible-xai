# SPDX-License-Identifier: Apache-2.0

"""Lock the xai-sdk surface aknochow.xai actually calls."""

from __future__ import annotations

import json
from importlib.metadata import version

from packaging.version import Version


def test_installed_sdk_meets_the_collection_floor():
    assert Version(version("xai-sdk")) >= Version("1.21.0")


def test_client_accepts_api_key_and_timeout():
    from xai_sdk import Client

    # Client is a thin wrapper; verify we can construct with explicit kwargs the module passes.
    Client(api_key="test-key", timeout=1.0, api_host="api.x.ai")


def test_chat_create_accepts_stream_and_encrypted_content():
    from xai_sdk import Client

    client = Client(api_key="test-key", timeout=1.0)
    chat = client.chat.create(
        model="grok-4.7",
        messages=[],
        temperature=0.7,
        top_p=0.95,
        use_encrypted_content=True,
    )
    assert callable(chat.stream)


def test_response_schema_matches_parse_proto_shape():
    """response_schema is a JSON schema dict encoded like Chat.parse, not a class."""
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        response_format_from_schema,
    )
    from xai_sdk.proto import chat_pb2

    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}, "required": ["answer"]}
    fmt = response_format_from_schema(schema)

    assert isinstance(fmt, chat_pb2.ResponseFormat)
    assert fmt.format_type == chat_pb2.FORMAT_TYPE_JSON_SCHEMA
    assert json.loads(fmt.schema) == schema


def test_tool_call_conversation_converts_with_the_real_sdk(monkeypatch):
    """Assistant tool_calls and tool results convert through the real xai_sdk.proto.

    Other test modules put fake ``xai_sdk`` modules in sys.modules, so remove
    them for this test (monkeypatch restores them) and import the real SDK.
    """
    import importlib
    import sys

    for name in [n for n in sys.modules if n == "xai_sdk" or n.startswith("xai_sdk.")]:
        monkeypatch.delitem(sys.modules, name)
    importlib.import_module("xai_sdk")
    from xai_sdk.proto import chat_pb2

    assert chat_pb2.ToolCall.DESCRIPTOR.full_name

    from ansible_collections.aknochow.xai.plugins.module_utils.grok_messages import (
        ansible_messages_to_proto,
    )

    messages = [
        {
            "role": "assistant",
            "content": "",
            "encrypted_content": "opaque-reasoning",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}},
                {"id": "call_2", "function": {"name": "grep", "arguments": '{"pattern": "x"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "file a"},
        {"role": "tool", "tool_call_id": "call_2", "content": "match"},
    ]
    assistant_msg, tool_one, tool_two = ansible_messages_to_proto(messages)

    assert assistant_msg.encrypted_content == "opaque-reasoning"
    calls = [(c.id, c.function.name, c.function.arguments) for c in assistant_msg.tool_calls]
    assert calls == [
        ("call_1", "read_file", '{"path": "a.py"}'),
        ("call_2", "grep", '{"pattern": "x"}'),
    ]
    assert tool_one.role == chat_pb2.ROLE_TOOL
    assert tool_two.role == chat_pb2.ROLE_TOOL
    assert [tool_one.tool_call_id, tool_two.tool_call_id] == ["call_1", "call_2"]
