"""Task polling utilities for async MiniMax operations (Video, T2A Async).

The MiniMax API uses an asynchronous task model for long-running operations:
``create()`` returns a ``task_id``, and the caller must repeatedly ``query()``
until the task reaches a terminal state (``Success`` or ``Fail``).

This module provides both sync and async polling loops that encapsulate that
pattern with configurable interval and timeout.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from minimax_sdk._http import AsyncHttpClient, HttpClient
from minimax_sdk.exceptions import MiniMaxError, PollTimeoutError

logger = logging.getLogger("minimax_sdk")

# Status values returned by the MiniMax query endpoints.
_PENDING_STATUSES: frozenset[str] = frozenset(
    {
        "Preparing",
        "Queueing",
        "Processing",
    }
)
_SUCCESS_STATUS: str = "Success"
_FAIL_STATUS: str = "Fail"


def poll_task(
    http_client: HttpClient,
    query_path: str,
    task_id: str,
    *,
    poll_interval: float = 5.0,
    poll_timeout: float = 600.0,
) -> dict[str, Any]:
    """Synchronously poll a MiniMax async task until completion.

    Parameters
    ----------
    http_client:
        The sync HTTP client to use for query requests.
    query_path:
        API path for the query endpoint (e.g. ``"/v1/query/video_generation"``).
    task_id:
        The task identifier returned by the creation endpoint.
    poll_interval:
        Seconds to sleep between polls.
    poll_timeout:
        Maximum total seconds to wait before raising :class:`PollTimeoutError`.

    Returns
    -------
    dict:
        The full API response body of the successful query.

    Raises
    ------
    PollTimeoutError:
        If the task does not reach a terminal state within *poll_timeout*.
    MiniMaxError:
        If the task reaches ``Fail`` status.
    """
    deadline = time.monotonic() + poll_timeout

    while True:
        body = http_client.request(
            "GET",
            query_path,
            params={"task_id": task_id},
        )

        status = body.get("status", "")

        if status == _SUCCESS_STATUS:
            logger.debug("Polling task_id=%s -> Success", task_id)
            return body

        if status == _FAIL_STATUS:
            base = body.get("base_resp", {})
            code = int(base.get("status_code", 0))
            msg = base.get("status_msg", "Task failed")
            trace_id = body.get("trace_id", base.get("trace_id", ""))
            raise MiniMaxError(msg, code=code, trace_id=trace_id)

        logger.debug("Polling task_id=%s -> %s", task_id, status or "unknown")

        if status not in _PENDING_STATUSES:
            # Unknown status — treat as still pending but log-worthy.
            pass

        time.sleep(poll_interval)

        if time.monotonic() > deadline:
            raise PollTimeoutError(
                f"Task {task_id} did not complete within {poll_timeout}s",
                code=0,
                trace_id="",
            )


async def async_poll_task(
    http_client: AsyncHttpClient,
    query_path: str,
    task_id: str,
    *,
    poll_interval: float = 5.0,
    poll_timeout: float = 600.0,
) -> dict[str, Any]:
    """Asynchronously poll a MiniMax async task until completion.

    Parameters
    ----------
    http_client:
        The async HTTP client to use for query requests.
    query_path:
        API path for the query endpoint (e.g. ``"/v1/query/video_generation"``).
    task_id:
        The task identifier returned by the creation endpoint.
    poll_interval:
        Seconds to sleep between polls.
    poll_timeout:
        Maximum total seconds to wait before raising :class:`PollTimeoutError`.

    Returns
    -------
    dict:
        The full API response body of the successful query.

    Raises
    ------
    PollTimeoutError:
        If the task does not reach a terminal state within *poll_timeout*.
    MiniMaxError:
        If the task reaches ``Fail`` status.
    """
    deadline = asyncio.get_running_loop().time() + poll_timeout

    while True:
        body = await http_client.request(
            "GET",
            query_path,
            params={"task_id": task_id},
        )

        status = body.get("status", "")

        if status == _SUCCESS_STATUS:
            logger.debug("Polling task_id=%s -> Success", task_id)
            return body

        if status == _FAIL_STATUS:
            base = body.get("base_resp", {})
            code = int(base.get("status_code", 0))
            msg = base.get("status_msg", "Task failed")
            trace_id = body.get("trace_id", base.get("trace_id", ""))
            raise MiniMaxError(msg, code=code, trace_id=trace_id)

        logger.debug("Polling task_id=%s -> %s", task_id, status or "unknown")

        if status not in _PENDING_STATUSES:
            pass

        await asyncio.sleep(poll_interval)

        if asyncio.get_running_loop().time() > deadline:
            raise PollTimeoutError(
                f"Task {task_id} did not complete within {poll_timeout}s",
                code=0,
                trace_id="",
            )
