# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_xai_sdk(monkeypatch):
    mock_sdk = MagicMock()
    monkeypatch.setitem(sys.modules, "xai_sdk", mock_sdk)
    monkeypatch.setitem(sys.modules, "xai_sdk.chat", MagicMock())
    monkeypatch.setitem(sys.modules, "xai_sdk.proto", MagicMock())
    chat_pb2 = MagicMock()
    chat_pb2.FORMAT_TYPE_JSON_OBJECT = 1
    chat_pb2.FORMAT_TYPE_TEXT = 2
    chat_pb2.FORMAT_TYPE_JSON_SCHEMA = 3
    chat_pb2.ResponseFormat = MagicMock
    monkeypatch.setitem(sys.modules, "xai_sdk.proto.chat_pb2", chat_pb2)

    from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

    # TestMain assigns these on the shared module. Put the real ones back after each test.
    monkeypatch.setattr(chat_module, "AnsibleModule", chat_module.AnsibleModule)
    monkeypatch.setattr(chat_module, "get_client", chat_module.get_client)
    return mock_sdk


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

    def test_structured_from_a_repeated_object(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules.chat import flatten_response

        text = '{"findings": []}{"findings": []}'
        result = flatten_response(make_response(content=text), parse_structured=True)

        assert result["structured"] == {"findings": []}
        assert result["text"] == text

    def test_tool_calls_flattened(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.modules.chat import flatten_response

        result = flatten_response(
            make_response(content="", tool_calls=[make_tool_call()]),
        )

        assert result["tool_calls"][0]["name"] == "get_weather"
        assert result["tool_calls"][0]["args"] == {"city": "Boston"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        (' {"a": 1}\n', {"a": 1}),
        ('{"a": 1}{"a": 1}', {"a": 1}),
        ('{"a": 1}\n{"a": 1}\n{"a": 1}', {"a": 1}),
        ('{"a": 1}{"a": 2}', None),
        ('{"a": 1} trailing', None),
        ('{"a": 1}{"a":', None),
        ("not json", None),
    ],
)
def test_parse_structured_text(mock_xai_sdk, text, expected):
    from ansible_collections.aknochow.xai.plugins.modules.chat import parse_structured_text

    assert parse_structured_text(text) == expected


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

        partial = make_response(content="partial answer", finish_reason="REASON_INVALID")

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


class StatusError(Exception):
    """Shaped like grpc.RpcError: a status from code() plus the status text."""

    def __init__(self, status):
        super().__init__(f"status = StatusCode.{status}, details = dropped")
        self._status = status

    def code(self):
        return _Status(self._status)


class _Status:
    def __init__(self, name):
        self.name = name


class FakeTime:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _attempt(*chunks, error=None, duration=0.0, clock=None):
    """One fake chat: yields chunks, spends duration on the clock, then maybe raises."""

    def stream():
        for chunk in chunks:
            yield chunk, MagicMock()
        if clock is not None:
            clock.now += duration
        if error is not None:
            raise error

    chat = MagicMock()
    chat.stream.side_effect = stream
    return chat


class TestRetryBudget:
    @pytest.fixture
    def clock(self, monkeypatch):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        fake = FakeTime()
        monkeypatch.setattr(chat_module, "time", fake)
        monkeypatch.setattr(chat_module.random, "uniform", lambda low, high: high)
        return fake

    def _run(self, monkeypatch, chats, timeout=100.0, max_retries=2, api_key="test-key"):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 16,
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        client = MagicMock()
        client.chat.create.side_effect = chats
        get_client = MagicMock(return_value=client)
        monkeypatch.setattr(chat_module, "AnsibleModule", MagicMock(return_value=module))
        monkeypatch.setattr(chat_module, "get_client", get_client)
        chat_module.main()
        # The first get_client call only validates. Later ones carry a deadline.
        deadlines = [c.kwargs["timeout"] for c in get_client.call_args_list[1:]]
        return module, client, deadlines

    def test_each_attempt_gets_only_the_remaining_time(self, monkeypatch, clock):
        chats = [
            _attempt(error=StatusError("INTERNAL"), duration=30.0, clock=clock),
            _attempt(error=StatusError("UNAVAILABLE"), duration=20.0, clock=clock),
            _attempt(make_response(content="pong")),
        ]

        module, _client, deadlines = self._run(monkeypatch, chats)

        # Budget 100, less 30 spent and a 1s backoff, then 20 spent and a 2s backoff.
        assert deadlines == [100.0, 69.0, 47.0]
        assert clock.sleeps == [1.0, 2.0]
        assert module.exit_json.call_args.kwargs["text"] == "pong"

    def test_total_time_never_passes_the_budget(self, monkeypatch, clock):
        """Each attempt runs until its deadline drops it. Three would be 300s without a budget."""
        started = clock.now
        deadlines_used = []

        def create(**_kwargs):
            deadline = deadlines_used[-1] if deadlines_used else None
            return _attempt(error=StatusError("UNAVAILABLE"), duration=deadline, clock=clock)

        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 16,
            "api_key": "test-key",
            "timeout": 100.0,
            "max_retries": 2,
        }

        def get_client(_module, timeout=None):
            deadlines_used.append(timeout)
            client = MagicMock()
            client.chat.create.side_effect = create
            return client

        monkeypatch.setattr(chat_module, "AnsibleModule", MagicMock(return_value=module))
        monkeypatch.setattr(chat_module, "get_client", get_client)
        chat_module.main()

        assert clock.now - started <= 100.0
        assert len(module.fail_json.call_args.kwargs["attempts"]) == 1

    def test_backoff_counts_against_the_budget(self, monkeypatch, clock):
        """10.5s is left, which is enough for an attempt but not after a 1s backoff."""
        chats = [_attempt(error=StatusError("INTERNAL"), duration=89.5, clock=clock), _attempt()]

        module, client, deadlines = self._run(monkeypatch, chats)

        assert deadlines == [100.0]
        assert client.chat.create.call_count == 1
        assert clock.sleeps == []
        failed = module.fail_json.call_args.kwargs
        assert "StatusCode.INTERNAL" in failed["msg"]

    def test_backoff_stays_bounded(self, monkeypatch, clock):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        assert [chat_module._backoff_seconds(i) for i in range(6)] == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]

    def test_backoff_has_jitter(self, monkeypatch):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        seen = {chat_module._backoff_seconds(2) for _round in range(20)}
        assert len(seen) > 1
        assert all(2.0 <= value <= 4.0 for value in seen)

    @pytest.mark.parametrize(
        "status",
        ["UNAUTHENTICATED", "PERMISSION_DENIED", "INVALID_ARGUMENT", "RESOURCE_EXHAUSTED", "NOT_FOUND"],
    )
    def test_non_transient_status_is_not_retried(self, monkeypatch, clock, status):
        chats = [_attempt(error=StatusError(status)), _attempt()]

        module, client, _deadlines = self._run(monkeypatch, chats)

        assert client.chat.create.call_count == 1
        assert clock.sleeps == []
        assert status in module.fail_json.call_args.kwargs["msg"]

    def test_status_code_beats_the_text(self, monkeypatch, clock):
        error = StatusError("INVALID_ARGUMENT")
        error.args = ("prompt mentioned UNAVAILABLE and RST_STREAM",)
        chats = [_attempt(error=error), _attempt()]

        _module, client, _deadlines = self._run(monkeypatch, chats)

        assert client.chat.create.call_count == 1

    def test_rst_stream_under_a_generic_status_is_retried(self, monkeypatch, clock):
        error = StatusError("UNKNOWN")
        error.args = ("Stream removed: RST_STREAM with error code 2",)
        chats = [_attempt(error=error), _attempt(make_response(content="pong"))]

        module, client, _deadlines = self._run(monkeypatch, chats)

        assert client.chat.create.call_count == 2
        assert module.exit_json.call_args.kwargs["text"] == "pong"

    def test_deadline_is_not_retried_and_keeps_partial_text(self, monkeypatch, clock):
        partial = make_response(
            content="partial answer", finish_reason="REASON_INVALID", usage_kwargs={"cost_in_usd_ticks": 7}
        )
        chats = [_attempt(partial, error=StatusError("DEADLINE_EXCEEDED")), _attempt()]

        module, client, _deadlines = self._run(monkeypatch, chats)

        assert client.chat.create.call_count == 1
        failed = module.fail_json.call_args.kwargs
        assert "client timeout of 100.0 seconds" in failed["msg"]
        assert failed["partial_text"] == "partial answer"
        assert failed["attempts"][0]["usage"]["cost_in_usd_ticks"] == 7

    def test_partial_text_survives_a_retry_that_received_nothing(self, monkeypatch, clock):
        chats = [
            _attempt(make_response(content="first try", finish_reason="REASON_INVALID"), error=StatusError("INTERNAL")),
            _attempt(error=StatusError("DEADLINE_EXCEEDED")),
        ]

        module, _client, _deadlines = self._run(monkeypatch, chats)

        failed = module.fail_json.call_args.kwargs
        assert "client timeout" in failed["msg"]
        assert failed["partial_text"] == "first try"

    def test_no_budget_starts_no_attempt(self, monkeypatch, clock):
        module, client, deadlines = self._run(monkeypatch, [_attempt()], timeout=0.0)

        assert deadlines == []
        client.chat.create.assert_not_called()
        failed = module.fail_json.call_args.kwargs
        assert "client timeout of 0.0 seconds" in failed["msg"]
        assert failed["attempts"] == []

    def test_attempts_on_success_after_a_retry(self, monkeypatch, clock):
        dropped_usage = {"prompt_tokens": 40, "total_tokens": 40, "cost_in_usd_ticks": 9}
        final_usage = {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55, "cost_in_usd_ticks": 11}
        chats = [
            _attempt(
                make_response(content="par", finish_reason="REASON_INVALID", usage_kwargs=dropped_usage),
                error=StatusError("INTERNAL"),
            ),
            _attempt(error=StatusError("UNAVAILABLE")),
            _attempt(make_response(content="pong", usage_kwargs=final_usage)),
        ]

        module, _client, _deadlines = self._run(monkeypatch, chats)

        result = module.exit_json.call_args.kwargs
        first, second, third = result["attempts"]
        assert first["usage"]["cost_in_usd_ticks"] == 9
        assert "StatusCode.INTERNAL" in first["error"]
        assert second == {"usage": None, "error": "status = StatusCode.UNAVAILABLE, details = dropped"}
        assert third["error"] is None
        assert third["usage"] == result["usage"]
        assert result["usage"]["cost_in_usd_ticks"] == 11

    def test_attempts_on_final_failure(self, monkeypatch, clock):
        chats = [
            _attempt(
                make_response(content="x", finish_reason="REASON_INVALID", usage_kwargs={"total_tokens": 40}),
                error=StatusError("INTERNAL"),
            ),
            _attempt(error=StatusError("INTERNAL")),
        ]

        module, _client, _deadlines = self._run(monkeypatch, chats, max_retries=1)

        failed = module.fail_json.call_args.kwargs
        assert [entry["error"] is not None for entry in failed["attempts"]] == [True, True]
        assert failed["attempts"][0]["usage"]["total_tokens"] == 40
        assert failed["attempts"][1]["usage"] is None
        assert failed["msg"] == "status = StatusCode.INTERNAL, details = dropped"

    def test_empty_stream_is_recorded_and_not_retried(self, monkeypatch, clock):
        module, client, _deadlines = self._run(monkeypatch, [_attempt(), _attempt()])

        assert client.chat.create.call_count == 1
        failed = module.fail_json.call_args.kwargs
        assert failed["attempts"] == [{"usage": None, "error": failed["msg"]}]

    def test_api_key_is_redacted_everywhere(self, monkeypatch, clock):
        secret = "xai-secret-value"
        error = StatusError("INTERNAL")
        error.args = (f"INTERNAL bad key {secret}",)
        chats = [_attempt(error=error), _attempt(error=error)]

        module, _client, _deadlines = self._run(monkeypatch, chats, max_retries=1, api_key=secret)

        failed = module.fail_json.call_args.kwargs
        assert secret not in json.dumps(failed)
        assert "<api_key>" in failed["msg"]
        assert "<api_key>" in failed["attempts"][0]["error"]

    def test_flatten_failure_keeps_the_finished_text(self, monkeypatch, clock):
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        secret = "xai-secret-value"

        def explode(_response, parse_structured=False):
            raise ValueError(f"cannot serialize {secret}")

        monkeypatch.setattr(chat_module, "flatten_response", explode)
        chats = [_attempt(make_response(content="finished answer", usage_kwargs={"total_tokens": 15}))]

        module, _client, _deadlines = self._run(monkeypatch, chats, api_key=secret)

        module.exit_json.assert_not_called()
        failed = module.fail_json.call_args.kwargs
        assert failed["partial_text"] == "finished answer"
        assert failed["attempts"] == [
            {"usage": failed["attempts"][0]["usage"], "error": "cannot serialize <api_key>"}
        ]
        assert failed["attempts"][0]["usage"]["total_tokens"] == 15
        assert secret not in json.dumps(failed)

    def test_failing_close_does_not_mask_the_result(self, monkeypatch, clock):
        client = MagicMock()
        client.close.side_effect = RuntimeError("close failed")
        client.chat.create.return_value = _attempt(make_response(content="pong"))
        from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 16,
            "api_key": "test-key",
            "timeout": 100.0,
        }
        monkeypatch.setattr(chat_module, "AnsibleModule", MagicMock(return_value=module))
        monkeypatch.setattr(chat_module, "get_client", MagicMock(return_value=client))
        chat_module.main()

        module.fail_json.assert_not_called()
        assert module.exit_json.call_args.kwargs["text"] == "pong"
