"""Tests for minimax_sdk._base — SyncResource, AsyncResource."""

from __future__ import annotations

from unittest.mock import MagicMock

from minimax_sdk._base import AsyncResource, SyncResource
from minimax_sdk._http import AsyncHttpClient, HttpClient


class TestSyncResource:
    def test_stores_http_and_client(self) -> None:
        mock_http = MagicMock(spec=HttpClient)
        mock_client = MagicMock()  # simulates MiniMax

        resource = SyncResource(mock_http, client=mock_client)

        assert resource._http is mock_http
        assert resource._client is mock_client

    def test_client_defaults_to_none(self) -> None:
        mock_http = MagicMock(spec=HttpClient)

        resource = SyncResource(mock_http)

        assert resource._http is mock_http
        assert resource._client is None


class TestAsyncResource:
    def test_stores_http_and_client(self) -> None:
        mock_http = MagicMock(spec=AsyncHttpClient)
        mock_client = MagicMock()  # simulates AsyncMiniMax

        resource = AsyncResource(mock_http, client=mock_client)

        assert resource._http is mock_http
        assert resource._client is mock_client

    def test_client_defaults_to_none(self) -> None:
        mock_http = MagicMock(spec=AsyncHttpClient)

        resource = AsyncResource(mock_http)

        assert resource._http is mock_http
        assert resource._client is None
