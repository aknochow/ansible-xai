# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_xai_sdk():
    mock_sdk = MagicMock()
    sys.modules["xai_sdk"] = mock_sdk
    sys.modules["xai_sdk.chat"] = MagicMock()
    sys.modules["xai_sdk.proto"] = MagicMock()
    chat_pb2 = MagicMock()
    chat_pb2.FORMAT_TYPE_JSON_OBJECT = 1
    chat_pb2.FORMAT_TYPE_TEXT = 2
    chat_pb2.FORMAT_TYPE_JSON_SCHEMA = 3
    chat_pb2.ResponseFormat = MagicMock
    sys.modules["xai_sdk.proto.chat_pb2"] = chat_pb2
    yield mock_sdk
    for name in list(sys.modules):
        if name == "xai_sdk" or name.startswith("xai_sdk."):
            sys.modules.pop(name, None)


def make_tool_call(call_id="call_1", name="get_weather", arguments='{"city": "Boston"}'):
    function = MagicMock()
    function.name = name
    function.arguments = arguments
    tool_call = MagicMock()
    tool_call.id = call_id
    tool_call.function = function
    return tool_call


def make_response(
    content="hello",
    reasoning_content=None,
    tool_calls=None,
    finish_reason="FINISH_REASON_STOP",
    usage_kwargs=None,
    encrypted_content="",
):
    response = MagicMock()
    response.content = content
    response.reasoning_content = reasoning_content or ""
    response.encrypted_content = encrypted_content
    response.tool_calls = tool_calls or []
    response.finish_reason = finish_reason
    usage = MagicMock()
    defaults = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "reasoning_tokens": 0,
        "cached_prompt_text_tokens": 2,
        "cost_in_usd_ticks": 0,
    }
    defaults.update(usage_kwargs or {})
    for key, value in defaults.items():
        setattr(usage, key, value)
    response.usage = usage
    response.proto = MagicMock()
    return response


class TestFlattenResponse:
    def test_text_only(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules.chat import flatten_response

        result = flatten_response(make_response(content="hello world"))

        assert result["text"] == "hello world"
        assert result["tool_calls"] == []
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["reasoning_tokens"] == 0
        assert result["usage"]["cost_in_usd_ticks"] == 0
        assert "reasoning" not in result

    def test_reasoning_included_when_present(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules.chat import flatten_response

        result = flatten_response(make_response(content="4", reasoning_content="2+2"))

        assert result["reasoning"] == "2+2"
        assert result["text"] == "4"

    def test_reasoning_tokens_returned(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules.chat import flatten_response

        result = flatten_response(
            make_response(content="4", reasoning_content="2+2", usage_kwargs={"reasoning_tokens": 18})
        )

        assert result["reasoning"] == "2+2"
        assert result["usage"]["reasoning_tokens"] == 18

    def test_structured_when_requested(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules.chat import flatten_response

        payload = {"name": "bug", "severity": "high"}
        result = flatten_response(
            make_response(content=json.dumps(payload)),
            parse_structured=True,
        )

        assert result["structured"] == payload

    def test_tool_calls_flattened(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules.chat import flatten_response

        result = flatten_response(
            make_response(content="", tool_calls=[make_tool_call()]),
        )

        assert result["tool_calls"][0]["name"] == "get_weather"
        assert result["tool_calls"][0]["args"] == {"city": "Boston"}


class TestMain:
    def test_chat_sample_success(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        mock_client = MagicMock()
        mock_chat = MagicMock()
        mock_response = make_response(content="ok", encrypted_content="opaque")
        mock_chat.stream.return_value = [(mock_response, MagicMock())]
        mock_client.chat.create.return_value = mock_chat

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 32,
            "api_key": "test-key",
            "api_host": "api.x.ai",
            "timeout": 120.0,
            "max_retries": 2,
            "temperature": None,
            "top_p": None,
            "stop_sequences": None,
            "response_format": None,
            "tools": None,
            "tool_choice": None,
            "reasoning_effort": None,
        }

        chat_module.AnsibleModule = MagicMock(return_value=module)
        chat_module.get_client = MagicMock(return_value=mock_client)
        chat_module.main()

        module.exit_json.assert_called_once()
        assert module.exit_json.call_args.kwargs["text"] == "ok"
        create_kwargs = mock_client.chat.create.call_args.kwargs
        assert create_kwargs["max_tokens"] == 32
        assert create_kwargs["temperature"] == 0.7
        assert create_kwargs["top_p"] == 0.95
        assert create_kwargs["use_encrypted_content"] is True
        assert create_kwargs["store_messages"] is False
        assert "reasoning_effort" not in create_kwargs
        assert "parallel_tool_calls" not in create_kwargs
        assert "response_format" not in create_kwargs
        assert module.exit_json.call_args.kwargs["encrypted_content"] == "opaque"
        mock_chat.sample.assert_not_called()

    def test_forwards_parity_arguments(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        schema = {
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
        }
        chat_pb2 = sys.modules["xai_sdk.proto.chat_pb2"]
        chat_pb2.FORMAT_TYPE_JSON_SCHEMA = "json_schema"
        chat_pb2.ResponseFormat = lambda **kwargs: ("format", kwargs)
        # `from xai_sdk.proto import chat_pb2` uses the parent attribute, not
        # only the sys.modules entry, when the parent is a MagicMock.
        sys.modules["xai_sdk.proto"].chat_pb2 = chat_pb2
        sdk_chat = sys.modules["xai_sdk.chat"]
        sdk_chat.tool = MagicMock(side_effect=lambda **kwargs: ("tool", kwargs))
        sdk_chat.required_tool = MagicMock(side_effect=lambda name: ("required", name))
        sdk_chat.user = MagicMock(side_effect=lambda *args: ("user", args))
        sdk_chat.image = MagicMock(side_effect=lambda url, detail="auto": ("image", url, detail))

        mock_client = MagicMock()
        mock_chat = MagicMock()
        mock_chat.stream.return_value = [
            (make_response(content='{"answer": 102}', reasoning_content="17*6"), MagicMock())
        ]
        mock_client.chat.create.return_value = mock_chat

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [
                {
                    "role": "user",
                    "content": "What is 17 * 6?",
                    "image_urls": ["https://example.com/board.png"],
                    "image_detail": "low",
                }
            ],
            "max_tokens": 128,
            "api_key": "test-key",
            "api_host": "api.x.ai",
            "timeout": 120.0,
            "max_retries": 2,
            "temperature": 0.7,
            "top_p": 0.95,
            "stop_sequences": ["END"],
            "response_schema": schema,
            "response_format": None,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "weather",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
            "parallel_tool_calls": False,
            "reasoning_effort": "low",
        }

        chat_module.AnsibleModule = MagicMock(return_value=module)
        chat_module.get_client = MagicMock(return_value=mock_client)
        chat_module.main()

        module.exit_json.assert_called_once()
        result = module.exit_json.call_args.kwargs
        assert result["structured"] == {"answer": 102}
        assert result["reasoning"] == "17*6"
        assert result["usage"]["reasoning_tokens"] == 0
        create_kwargs = mock_client.chat.create.call_args.kwargs
        assert create_kwargs["max_tokens"] == 128
        assert create_kwargs["temperature"] == 0.7
        assert create_kwargs["top_p"] == 0.95
        assert create_kwargs["stop"] == ["END"]
        assert create_kwargs["parallel_tool_calls"] is False
        assert create_kwargs["reasoning_effort"] == "low"
        assert create_kwargs["use_encrypted_content"] is True
        assert create_kwargs["store_messages"] is False
        assert create_kwargs["tool_choice"] == ("required", "get_weather")
        assert create_kwargs["tools"][0][1]["name"] == "get_weather"
        encoded = json.dumps(schema)
        assert create_kwargs["response_format"] == (
            "format",
            {"format_type": "json_schema", "schema": encoded},
        )
        assert create_kwargs["messages"] == [
            (
                "user",
                (
                    "What is 17 * 6?",
                    ("image", "https://example.com/board.png", "low"),
                ),
            )
        ]

    def test_mutually_exclusive_schema_args(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 32,
            "api_key": "test-key",
            "stop_sequences": None,
            "reasoning_effort": None,
            "response_schema": {"type": "object"},
            "response_format": {"type": "json_object"},
        }
        chat_module.AnsibleModule = MagicMock(return_value=module)
        chat_module.get_client = MagicMock()
        chat_module.main()

        module.fail_json.assert_called_once()
        assert "mutually exclusive" in module.fail_json.call_args.kwargs["msg"]
        chat_module.get_client.assert_not_called()

    def test_retries_a_transient_stream_reset(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        mock_client = MagicMock()
        failed = MagicMock()
        failed.stream.side_effect = RuntimeError("StatusCode.INTERNAL RST_STREAM")
        ok = MagicMock()
        ok.stream.return_value = [(make_response(content="pong"), MagicMock())]
        mock_client.chat.create.side_effect = [failed, ok]

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 16,
            "api_key": "test-key",
            "api_host": "api.x.ai",
            "timeout": 30.0,
            "max_retries": 2,
            "temperature": None,
            "top_p": None,
            "stop_sequences": None,
            "response_format": None,
            "response_schema": None,
            "tools": None,
            "tool_choice": None,
            "parallel_tool_calls": None,
            "reasoning_effort": None,
            "use_encrypted_content": True,
        }
        chat_module.AnsibleModule = MagicMock(return_value=module)
        chat_module.get_client = MagicMock(return_value=mock_client)
        chat_module.main()

        module.exit_json.assert_called_once()
        assert module.exit_json.call_args.kwargs["text"] == "pong"
        assert mock_client.chat.create.call_count == 2

    def test_missing_api_key_in_main(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 32,
            "api_key": None,
            "api_host": "api.x.ai",
            "timeout": 120.0,
            "max_retries": 2,
        }

        chat_module.AnsibleModule = MagicMock(return_value=module)

        def fail_client(mod):
            mod.fail_json(msg="missing key")
            return None

        chat_module.get_client = fail_client
        chat_module.main()
        module.fail_json.assert_called()

    def test_empty_stream_fails(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        mock_client = MagicMock()
        mock_chat = MagicMock()
        mock_chat.stream.return_value = []
        mock_client.chat.create.return_value = mock_chat
        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 32,
            "api_key": "test-key",
            "timeout": 900.0,
        }
        chat_module.AnsibleModule = MagicMock(return_value=module)
        chat_module.get_client = MagicMock(return_value=mock_client)
        chat_module.main()

        module.fail_json.assert_called_once()
        assert "before any response chunk" in module.fail_json.call_args.kwargs["msg"]
        module.exit_json.assert_not_called()

    def test_deadline_reports_timeout_and_partial_text(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        class Deadline(Exception):
            def __str__(self):
                return "DEADLINE_EXCEEDED:Deadline Exceeded"

        partial = make_response(content="partial answer")

        def chunks():
            yield partial, MagicMock()
            raise Deadline()

        mock_client = MagicMock()
        mock_chat = MagicMock()
        mock_chat.stream.return_value = chunks()
        mock_client.chat.create.return_value = mock_chat
        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 32,
            "api_key": "test-key",
            "timeout": 900.0,
        }
        chat_module.AnsibleModule = MagicMock(return_value=module)
        chat_module.get_client = MagicMock(return_value=mock_client)
        chat_module.main()

        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        failed = module.fail_json.call_args.kwargs
        assert "timeout of 900.0 seconds" in failed["msg"]
        assert failed["partial_text"] == "partial answer"
