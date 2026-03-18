"""Shared fixtures for minimax-sdk tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from minimax_sdk._http import AsyncHttpClient, HttpClient
from minimax_sdk.client import MiniMax


@pytest.fixture()
def mock_http_client() -> MagicMock:
    """A mocked synchronous HttpClient."""
    client = MagicMock(spec=HttpClient)
    client.api_key = "test-key"
    client.base_url = "https://api.minimax.io"
    client.max_retries = 2
    return client


@pytest.fixture()
def mock_async_http_client() -> AsyncMock:
    """A mocked asynchronous AsyncHttpClient."""
    client = AsyncMock(spec=AsyncHttpClient)
    client.api_key = "test-key"
    client.base_url = "https://api.minimax.io"
    client.max_retries = 2
    return client


@pytest.fixture()
def minimax_client(monkeypatch: pytest.MonkeyPatch) -> MiniMax:
    """A MiniMax client initialised with a fake API key.

    Environment variables are cleared so configuration tests remain
    deterministic.
    """
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    monkeypatch.delenv("MINIMAX_MAX_RETRIES", raising=False)
    monkeypatch.delenv("MINIMAX_POLL_INTERVAL", raising=False)
    monkeypatch.delenv("MINIMAX_POLL_TIMEOUT", raising=False)
    monkeypatch.delenv("MINIMAX_TIMEOUT_CONNECT", raising=False)
    monkeypatch.delenv("MINIMAX_TIMEOUT_READ", raising=False)
    monkeypatch.delenv("MINIMAX_TIMEOUT_WRITE", raising=False)
    monkeypatch.delenv("MINIMAX_TIMEOUT_POOL", raising=False)

    return MiniMax(api_key="sk-test-fake-key")
