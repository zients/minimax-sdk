"""Base resource classes for the MiniMax SDK.

Every resource (Speech, Voice, Video, etc.) inherits from ``SyncResource`` or
``AsyncResource`` to gain access to the shared HTTP client and common helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from minimax_sdk._http import AsyncHttpClient, HttpClient

if TYPE_CHECKING:
    from minimax_sdk.client import AsyncMiniMax, MiniMax


class SyncResource:
    """Base class for synchronous API resources.

    Holds a reference to a :class:`HttpClient` (as ``_http``) and optionally
    the top-level :class:`MiniMax` client (as ``_client``) for cross-resource
    delegation.
    """

    def __init__(self, http_client: HttpClient, client: MiniMax | None = None) -> None:
        self._http = http_client
        self._client = client


class AsyncResource:
    """Base class for asynchronous API resources.

    Holds a reference to an :class:`AsyncHttpClient` (as ``_http``) and
    optionally the top-level :class:`AsyncMiniMax` client (as ``_client``)
    for cross-resource delegation.
    """

    def __init__(self, http_client: AsyncHttpClient, client: AsyncMiniMax | None = None) -> None:
        self._http = http_client
        self._client = client
