# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_xai_sdk(monkeypatch):
    mock_sdk = MagicMock()
    mock_client = MagicMock()
    mock_sdk.Client.return_value = mock_client
    monkeypatch.setitem(sys.modules, "xai_sdk", mock_sdk)
    monkeypatch.setitem(sys.modules, "xai_sdk.chat", MagicMock())
    monkeypatch.setitem(sys.modules, "xai_sdk.proto", MagicMock())
    monkeypatch.setitem(sys.modules, "xai_sdk.proto.chat_pb2", MagicMock())
    return mock_sdk


class TestProviderArgspec:
    def test_api_key_no_log_and_env_fallback(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import (
            PROVIDER_ARGSPEC,
        )

        assert PROVIDER_ARGSPEC["api_key"]["no_log"] is True
        assert PROVIDER_ARGSPEC["api_key"]["fallback"][1][0] == "GROK_API_KEY"
        assert "XAI_API_KEY" in PROVIDER_ARGSPEC["api_key"]["fallback"][1]
        assert "ANSIBLE_GROK_API_KEY" in PROVIDER_ARGSPEC["api_key"]["fallback"][1]

    def test_timeout_default(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import (
            PROVIDER_ARGSPEC,
        )

        assert PROVIDER_ARGSPEC["timeout"]["default"] == 900.0


class TestGetClient:
    def test_builds_client_with_resolved_key(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "api_key": "secret-key",
            "api_host": "api.x.ai",
            "timeout": 60.0,
            "max_retries": 2,
        }

        get_client(module)
        mock_xai_sdk.Client.assert_called_once_with(
            api_key="secret-key",
            api_host="api.x.ai",
            timeout=60.0,
            metadata=None,
        )

    def test_conversation_id_sets_cache_metadata(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "api_key": "secret-key",
            "api_host": "api.x.ai",
            "timeout": 60.0,
            "max_retries": 2,
            "conversation_id": "review-1-explore",
        }

        get_client(module)
        mock_xai_sdk.Client.assert_called_once_with(
            api_key="secret-key",
            api_host="api.x.ai",
            timeout=60.0,
            metadata=(("x-grok-conv-id", "review-1-explore"),),
        )

    def test_missing_api_key_fails(self, mock_xai_sdk):
        from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "api_key": None,
            "api_host": "api.x.ai",
            "timeout": 120.0,
            "max_retries": 2,
        }

        result = get_client(module)
        module.fail_json.assert_called_once()
        assert "GROK_API_KEY" in module.fail_json.call_args.kwargs["msg"]
        assert result is None

    def test_missing_sdk_fails_cleanly(self, mock_xai_sdk, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "xai_sdk":
                raise ImportError("no xai_sdk")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import (
            get_client,
        )

        module = MagicMock()
        module.params = {
            "api_key": "key",
            "api_host": "api.x.ai",
            "timeout": 120.0,
            "max_retries": 2,
        }

        result = get_client(module)
        module.fail_json.assert_called_once()
        assert "xai-sdk" in module.fail_json.call_args.kwargs["msg"]
        assert result is None


def test_timeout_argument_overrides_the_module_timeout(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import get_client

    module = MagicMock()
    module.params = {"api_key": "test-key", "api_host": "api.x.ai", "timeout": 900.0}

    get_client(module, timeout=12.5)

    assert mock_xai_sdk.Client.call_args.kwargs["timeout"] == 12.5


@pytest.mark.parametrize("value", ["a\nb", "trailing\n", "tab\there", "caf\u00e9", "del\x7f"])
def test_invalid_conversation_id_fails_before_any_client(mock_xai_sdk, value):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import get_client

    module = MagicMock()
    module.params = {"api_key": "test-key", "timeout": 60.0, "conversation_id": value}

    assert get_client(module) is None
    assert "conversation_id" in module.fail_json.call_args.kwargs["msg"]
    mock_xai_sdk.Client.assert_not_called()


def test_every_printable_ascii_conversation_id_is_accepted(mock_xai_sdk):
    from ansible_collections.aknochow.xai.plugins.module_utils.grok_client import get_client

    value = "".join(chr(code) for code in range(0x21, 0x7f))
    module = MagicMock()
    module.params = {"api_key": "test-key", "timeout": 60.0, "conversation_id": value}

    get_client(module)

    module.fail_json.assert_not_called()
    assert mock_xai_sdk.Client.call_args.kwargs["metadata"] == (("x-grok-conv-id", value),)
