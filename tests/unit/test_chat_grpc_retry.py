# SPDX-License-Identifier: Apache-2.0

"""Run chat.main against the real xai-sdk and a local gRPC server.

Nothing here reaches the network beyond localhost, and no real key is used.
Fake modules hid a real import bug once, so these use real status objects,
the real SDK deadline interceptor, and the real get_client.
"""

from __future__ import annotations

import functools
import importlib
import sys
import time
from concurrent import futures
from unittest.mock import MagicMock

import grpc
import pytest

SECRET = "xai-local-test-secret"


class ScriptedChat:
    """Plays one scripted step per call and records the deadline it saw."""

    def __init__(self, chat_pb2, steps):
        self.chat_pb2 = chat_pb2
        self.steps = list(steps)
        self.deadlines = []

    def chunk(self, text, finish=None, **usage):
        pb = self.chat_pb2
        return pb.GetChatCompletionChunk(
            id="local",
            outputs=[
                pb.CompletionOutputChunk(
                    delta=pb.Delta(content=text, role=pb.ROLE_ASSISTANT),
                    finish_reason=finish or "REASON_INVALID",
                )
            ],
            usage=usage or None,
        )

    def GetCompletionChunk(self, request, context):
        self.deadlines.append(context.time_remaining())
        yield from self.steps.pop(0)(self, context)


def text_then_stop(text, finish="REASON_STOP", **usage):
    def step(servicer, _context):
        yield servicer.chunk(text, finish=finish, **usage)

    return step


def clean_end(text, **usage):
    """The stream closes with OK, but no chunk carried a finish reason."""

    def step(servicer, _context):
        yield servicer.chunk(text, **usage)

    return step


def usage_only_end(**usage):
    def step(servicer, _context):
        yield servicer.chat_pb2.GetChatCompletionChunk(id="local", usage=usage)

    return step


def finish_then_abort(text, status, details="late drop", finish="REASON_STOP", **usage):
    def step(servicer, context):
        yield servicer.chunk(text, finish=finish, **usage)
        context.abort(status, details)

    return step


def abort(status, details="stream dropped", *, text=None, delay=0.0, **usage):
    def step(servicer, context):
        if text is not None:
            yield servicer.chunk(text, **usage)
        time.sleep(delay)
        context.abort(status, details)

    return step


def hang(text, seconds, finish=None):
    def step(servicer, _context):
        yield servicer.chunk(text, finish=finish)
        time.sleep(seconds)

    return step


@pytest.fixture
def run_chat(monkeypatch):
    """Serve the scripted steps and run chat.main through the real SDK."""
    for name in [n for n in sys.modules if n == "xai_sdk" or n.startswith("xai_sdk.")]:
        monkeypatch.delitem(sys.modules, name)
    xai_sdk = importlib.import_module("xai_sdk")
    from ansible_collections.aknochow.xai.plugins.module_utils import grok_client
    from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module
    from xai_sdk.proto import chat_pb2, chat_pb2_grpc

    assert chat_module.get_client is grok_client.get_client
    monkeypatch.setattr(xai_sdk, "Client", functools.partial(xai_sdk.Client, use_insecure_channel=True))
    monkeypatch.setattr(chat_module, "_BACKOFF_BASE_SECONDS", 0.01)

    class Servicer(ScriptedChat, chat_pb2_grpc.ChatServicer):
        pass

    servers = []

    def run(steps, timeout=30.0, max_retries=2, **params):
        servicer = Servicer(chat_pb2, steps)
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        chat_pb2_grpc.add_ChatServicer_to_server(servicer, server)
        port = server.add_insecure_port("localhost:0")
        server.start()
        servers.append(server)

        module = MagicMock()
        module.params = {
            "model": "grok-4.7",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 16,
            "api_key": SECRET,
            "api_host": f"localhost:{port}",
            "timeout": timeout,
            "max_retries": max_retries,
            **params,
        }
        monkeypatch.setattr(chat_module, "AnsibleModule", MagicMock(return_value=module))
        chat_module.main()
        return module, servicer

    yield run
    for server in servers:
        server.stop(grace=None)


def test_each_real_rpc_sees_only_the_remaining_deadline(run_chat):
    module, servicer = run_chat(
        [
            abort(grpc.StatusCode.INTERNAL, delay=1.0),
            abort(grpc.StatusCode.INTERNAL, delay=1.0),
            text_then_stop("pong", total_tokens=9, cost_in_usd_ticks=3),
        ]
    )

    module.fail_json.assert_not_called()
    result = module.exit_json.call_args.kwargs
    assert result["text"] == "pong"
    first, second, third = servicer.deadlines
    # Each attempt spent 1s. A fresh deadline per attempt would read about 30 here.
    # The margin covers the rounding in the grpc-timeout header.
    assert first <= 30.0
    assert second <= first - 0.9
    assert third <= second - 0.9


def test_real_transient_status_keeps_its_text_on_final_failure(run_chat):
    module, servicer = run_chat([abort(grpc.StatusCode.INTERNAL)] * 2, max_retries=1)

    assert len(servicer.deadlines) == 2
    failed = module.fail_json.call_args.kwargs
    assert "StatusCode.INTERNAL" in failed["msg"]
    assert "stream dropped" in failed["msg"]
    assert [entry["usage"] for entry in failed["attempts"]] == [None, None]


@pytest.mark.parametrize(
    "status",
    [
        grpc.StatusCode.UNAUTHENTICATED,
        grpc.StatusCode.PERMISSION_DENIED,
        grpc.StatusCode.INVALID_ARGUMENT,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
    ],
)
def test_real_non_transient_status_is_not_retried(run_chat, status):
    # The details name a transient status. Only the code may decide.
    module, servicer = run_chat([abort(status, "mentions UNAVAILABLE and RST_STREAM")])

    assert len(servicer.deadlines) == 1
    assert f"StatusCode.{status.name}" in module.fail_json.call_args.kwargs["msg"]


def test_real_deadline_is_not_retried_and_returns_partial_text(run_chat):
    module, servicer = run_chat([hang("partial answer", 3.0)], timeout=1.0)

    assert len(servicer.deadlines) == 1
    failed = module.fail_json.call_args.kwargs
    assert "client timeout of 1.0 seconds" in failed["msg"]
    assert failed["partial_text"] == "partial answer"
    assert "DEADLINE_EXCEEDED" in failed["attempts"][0]["error"]


def test_real_midstream_drop_reports_received_usage_and_redacts(run_chat):
    module, _servicer = run_chat(
        [
            abort(grpc.StatusCode.INTERNAL, f"bad {SECRET}", text="par", prompt_tokens=40, cost_in_usd_ticks=9),
            abort(grpc.StatusCode.INTERNAL, f"bad {SECRET}", text="tial"),
        ],
        max_retries=1,
    )

    failed = module.fail_json.call_args.kwargs
    first, second = failed["attempts"]
    assert first["usage"]["prompt_tokens"] == 40
    assert first["usage"]["cost_in_usd_ticks"] == 9
    # A chunk arrived with no usage on it, so nothing was measured.
    assert second["usage"] is None
    assert failed["partial_text"] == "tial"
    assert SECRET not in failed["msg"]
    assert SECRET not in first["error"]
    assert "<api_key>" in failed["msg"]


@pytest.mark.parametrize("status", [grpc.StatusCode.INTERNAL, grpc.StatusCode.UNAVAILABLE])
@pytest.mark.parametrize("finish", ["REASON_STOP", "REASON_TOOL_CALLS"])
def test_real_finished_response_survives_a_late_drop(run_chat, status, finish):
    module, servicer = run_chat(
        [finish_then_abort("done", status, f"late {SECRET}", finish=finish, total_tokens=9, cost_in_usd_ticks=3)]
    )

    module.fail_json.assert_not_called()
    assert len(servicer.deadlines) == 1
    result = module.exit_json.call_args.kwargs
    assert result["text"] == "done"
    assert result["finish_reason"] == finish
    assert result["usage"]["cost_in_usd_ticks"] == 3
    only = result["attempts"][0]
    assert len(result["attempts"]) == 1
    assert only["usage"] == result["usage"]
    assert f"StatusCode.{status.name}" in only["error"]
    assert SECRET not in only["error"]


def test_real_finished_response_survives_the_deadline(run_chat):
    module, servicer = run_chat([hang("done", 3.0, finish="REASON_STOP")], timeout=1.0)

    module.fail_json.assert_not_called()
    assert len(servicer.deadlines) == 1
    result = module.exit_json.call_args.kwargs
    assert result["text"] == "done"
    assert "DEADLINE_EXCEEDED" in result["attempts"][0]["error"]


def test_real_late_drop_without_a_finish_reason_is_still_retried(run_chat):
    module, servicer = run_chat(
        [abort(grpc.StatusCode.INTERNAL, text="trunc", total_tokens=4), text_then_stop("pong", total_tokens=9)]
    )

    assert len(servicer.deadlines) == 2
    result = module.exit_json.call_args.kwargs
    assert result["text"] == "pong"
    assert "StatusCode.INTERNAL" in result["attempts"][0]["error"]
    assert result["attempts"][1]["error"] is None


@pytest.mark.parametrize(
    "unfinished",
    [clean_end("trunc", total_tokens=4), usage_only_end(total_tokens=4)],
    ids=["truncated-text", "usage-only"],
)
def test_real_clean_end_without_a_finish_reason_is_retried(run_chat, unfinished):
    module, servicer = run_chat([unfinished, text_then_stop("pong", total_tokens=9)])

    module.fail_json.assert_not_called()
    assert len(servicer.deadlines) == 2
    result = module.exit_json.call_args.kwargs
    assert result["text"] == "pong"
    assert result["finish_reason"] == "REASON_STOP"
    first, second = result["attempts"]
    assert "finish reason" in first["error"]
    assert first["usage"]["total_tokens"] == 4
    assert second["error"] is None


def test_real_clean_end_without_a_finish_reason_fails_with_partial_text(run_chat):
    module, servicer = run_chat([clean_end("trunc")] * 2, max_retries=1)

    module.exit_json.assert_not_called()
    assert len(servicer.deadlines) == 2
    failed = module.fail_json.call_args.kwargs
    assert "finish reason" in failed["msg"]
    assert failed["partial_text"] == "trunc"
    assert [entry["error"] for entry in failed["attempts"]] == [failed["msg"]] * 2


def test_real_max_len_is_returned_for_the_caller_to_flag(run_chat):
    module, servicer = run_chat([text_then_stop("cut", finish="REASON_MAX_LEN", total_tokens=16)])

    module.fail_json.assert_not_called()
    assert len(servicer.deadlines) == 1
    result = module.exit_json.call_args.kwargs
    assert result["text"] == "cut"
    assert result["finish_reason"] == "REASON_MAX_LEN"
    assert result["attempts"][0]["error"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"messages": [{"role": "tool", "content": "x", "tool_call_id": 7}]},
        {"messages": [{"role": 7, "content": "x"}]},
        {"tools": [{"type": "function", "function": "not-a-dict"}]},
    ],
    ids=["integer-tool-call-id", "integer-role", "string-function"],
)
def test_real_bad_conversion_fails_clearly_without_a_call(run_chat, params):
    module, servicer = run_chat([], **params)

    assert servicer.deadlines == []
    module.fail_json.assert_called_once()
    assert module.fail_json.call_args.kwargs["msg"].startswith("Could not convert messages or tools")


def test_conversion_failure_redacts_the_key(run_chat, monkeypatch):
    from ansible_collections.aknochow.xai.plugins.modules import chat as chat_module

    def explode(_messages):
        raise TypeError(f"bad value {SECRET}")

    monkeypatch.setattr(chat_module, "ansible_messages_to_proto", explode)
    module, servicer = run_chat([])

    assert servicer.deadlines == []
    msg = module.fail_json.call_args.kwargs["msg"]
    assert SECRET not in msg
    assert "<api_key>" in msg


def test_real_invalid_conversation_id_makes_no_call(run_chat):
    module, servicer = run_chat([], conversation_id="line\nbreak")

    assert servicer.deadlines == []
    module.fail_json.assert_called_once()
    assert "conversation_id" in module.fail_json.call_args.kwargs["msg"]
    module.exit_json.assert_not_called()
