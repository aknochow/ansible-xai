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
