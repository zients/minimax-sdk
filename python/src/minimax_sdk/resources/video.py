"""Video resource — text-to-video, image-to-video, frames-to-video, and subject-to-video.

Provides both synchronous (`Video`) and asynchronous (`AsyncVideo`) clients.
High-level methods compose: ``create()`` -> poll loop -> ``files.retrieve()``
to return a fully-resolved :class:`VideoResult` with a download URL.
"""

from __future__ import annotations

from typing import Any

from .._base import AsyncResource, SyncResource
from .._polling import async_poll_task, poll_task
from ..types.video import VideoResult


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_request_body(
    *,
    model: str,
    prompt: str | None = None,
    prompt_optimizer: bool | None = None,
    fast_pretreatment: bool | None = None,
    duration: int | None = None,
    resolution: str | None = None,
    callback_url: str | None = None,
    first_frame_image: str | None = None,
    last_frame_image: str | None = None,
    subject_reference: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the JSON request body, omitting ``None`` values."""
    body: dict[str, Any] = {"model": model}
    if prompt is not None:
        body["prompt"] = prompt
    if prompt_optimizer is not None:
        body["prompt_optimizer"] = prompt_optimizer
    if fast_pretreatment is not None:
        body["fast_pretreatment"] = fast_pretreatment
    if duration is not None:
        body["duration"] = duration
    if resolution is not None:
        body["resolution"] = resolution
    if callback_url is not None:
        body["callback_url"] = callback_url
    if first_frame_image is not None:
        body["first_frame_image"] = first_frame_image
    if last_frame_image is not None:
        body["last_frame_image"] = last_frame_image
    if subject_reference is not None:
        body["subject_reference"] = subject_reference
    return body


_CREATE_PATH = "/v1/video_generation"
_QUERY_PATH = "/v1/query/video_generation"


# ── Sync ─────────────────────────────────────────────────────────────────────


class Video(SyncResource):
    """Synchronous video generation resource.

    High-level methods (``text_to_video``, ``image_to_video``,
    ``frames_to_video``, ``subject_to_video``) automatically poll until
    the generation task completes and return a :class:`VideoResult` with
    a temporary download URL.

    Low-level methods (``create``, ``query``) give direct access to the
    underlying API endpoints.
    """

    # ── Low-level ────────────────────────────────────────────────────────

    def create(self, **kwargs: Any) -> dict[str, Any]:
        """Create a video generation task.

        Sends a ``POST`` to ``/v1/video_generation`` with the supplied
        keyword arguments as the JSON body.

        Returns:
            The raw API response dict containing ``task_id``.
        """
        return self._http.request("POST", _CREATE_PATH, json=kwargs)

    def query(self, task_id: str) -> dict[str, Any]:
        """Query the status of a video generation task.

        Sends a ``GET`` to ``/v1/query/video_generation``.

        Args:
            task_id: The task identifier returned by :meth:`create`.

        Returns:
            The raw API response dict containing ``status``, and on
            success ``file_id``, ``video_width``, ``video_height``.
        """
        return self._http.request("GET", _QUERY_PATH, params={"task_id": task_id})

    # ── Private helper ───────────────────────────────────────────────────

    def _generate(
        self,
        body: dict[str, Any],
        *,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Shared pipeline: create -> poll -> retrieve -> VideoResult.

        Args:
            body: JSON body for the ``POST /v1/video_generation`` request.
            poll_interval: Seconds between status queries.  Falls back to
                the client-level ``poll_interval`` default.
            poll_timeout: Maximum seconds to wait before raising
                :class:`PollTimeoutError`.  Falls back to the client-level
                ``poll_timeout`` default.

        Returns:
            A :class:`VideoResult` with the download URL resolved.
        """
        # 1. Create the generation task.
        create_resp = self.create(**body)
        task_id: str = create_resp["task_id"]

        # 2. Poll until the task reaches a terminal state.
        interval = poll_interval if poll_interval is not None else self._client.poll_interval
        timeout = poll_timeout if poll_timeout is not None else self._client.poll_timeout

        poll_resp = poll_task(
            self._http,
            _QUERY_PATH,
            task_id,
            poll_interval=interval,
            poll_timeout=timeout,
        )

        # 3. Retrieve the file to obtain a download URL.
        file_id: str = poll_resp["file_id"]
        file_info = self._client.files.retrieve(file_id)

        return VideoResult(
            task_id=task_id,
            status=poll_resp["status"],
            file_id=file_id,
            download_url=file_info.download_url,
            video_width=poll_resp["video_width"],
            video_height=poll_resp["video_height"],
        )

    # ── High-level ───────────────────────────────────────────────────────

    def text_to_video(
        self,
        prompt: str,
        model: str = "MiniMax-Hailuo-2.3",
        *,
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        duration: int = 6,
        resolution: str | None = None,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video from a text prompt (T2V).

        Creates a generation task, polls until completion, and resolves
        the file download URL.

        Args:
            prompt: Text description of the desired video content.
            model: Model identifier. Defaults to ``"MiniMax-Hailuo-2.3"``.
            prompt_optimizer: Whether to optimize the prompt server-side.
            fast_pretreatment: Enable fast pre-treatment mode.
            duration: Video duration in seconds (default ``6``).
            resolution: Output resolution (e.g. ``"1280x720"``).
                ``None`` lets the API choose the default.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            fast_pretreatment=fast_pretreatment,
            duration=duration,
            resolution=resolution,
            callback_url=callback_url,
        )
        return self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    def image_to_video(
        self,
        first_frame_image: str,
        model: str = "MiniMax-Hailuo-2.3",
        *,
        prompt: str | None = None,
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        duration: int = 6,
        resolution: str | None = None,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video from a first-frame image (I2V).

        Creates a generation task, polls until completion, and resolves
        the file download URL.

        Args:
            first_frame_image: URL or base64 data URI of the first frame.
            model: Model identifier. Defaults to ``"MiniMax-Hailuo-2.3"``.
            prompt: Optional text prompt to guide generation.
            prompt_optimizer: Whether to optimize the prompt server-side.
            fast_pretreatment: Enable fast pre-treatment mode.
            duration: Video duration in seconds (default ``6``).
            resolution: Output resolution (e.g. ``"1280x720"``).
                ``None`` lets the API choose the default.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            fast_pretreatment=fast_pretreatment,
            duration=duration,
            resolution=resolution,
            callback_url=callback_url,
            first_frame_image=first_frame_image,
        )
        return self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    def frames_to_video(
        self,
        last_frame_image: str,
        *,
        first_frame_image: str | None = None,
        model: str = "MiniMax-Hailuo-02",
        prompt: str | None = None,
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        duration: int = 6,
        resolution: str | None = None,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video from frame endpoints (FL2V).

        Interpolates between an optional first frame and a required last
        frame to produce a video.

        Args:
            last_frame_image: URL or base64 data URI of the last frame
                (required).
            first_frame_image: URL or base64 data URI of the first frame
                (optional).
            model: Model identifier. Defaults to ``"MiniMax-Hailuo-02"``.
            prompt: Optional text prompt to guide generation.
            prompt_optimizer: Whether to optimize the prompt server-side.
            fast_pretreatment: Enable fast pre-treatment mode.
            duration: Video duration in seconds (default ``6``).
            resolution: Output resolution (e.g. ``"1280x720"``).
                ``None`` lets the API choose the default.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            fast_pretreatment=fast_pretreatment,
            duration=duration,
            resolution=resolution,
            callback_url=callback_url,
            first_frame_image=first_frame_image,
            last_frame_image=last_frame_image,
        )
        return self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    def subject_to_video(
        self,
        subject_reference: list[dict[str, Any]],
        *,
        prompt: str | None = None,
        model: str = "S2V-01",
        prompt_optimizer: bool = True,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video driven by subject references (S2V).

        Uses one or more subject reference images to drive video generation.

        Args:
            subject_reference: List of subject reference dicts, each
                containing ``"type"`` and ``"image"`` keys.
            prompt: Optional text prompt to guide generation.
            model: Model identifier. Defaults to ``"S2V-01"``.
            prompt_optimizer: Whether to optimize the prompt server-side.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            callback_url=callback_url,
            subject_reference=subject_reference,
        )
        return self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )


# ── Async ────────────────────────────────────────────────────────────────────


class AsyncVideo(AsyncResource):
    """Asynchronous video generation resource.

    High-level methods (``text_to_video``, ``image_to_video``,
    ``frames_to_video``, ``subject_to_video``) automatically poll until
    the generation task completes and return a :class:`VideoResult` with
    a temporary download URL.

    Low-level methods (``create``, ``query``) give direct access to the
    underlying API endpoints.
    """

    # ── Low-level ────────────────────────────────────────────────────────

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        """Create a video generation task.

        Sends a ``POST`` to ``/v1/video_generation`` with the supplied
        keyword arguments as the JSON body.

        Returns:
            The raw API response dict containing ``task_id``.
        """
        return await self._http.request("POST", _CREATE_PATH, json=kwargs)

    async def query(self, task_id: str) -> dict[str, Any]:
        """Query the status of a video generation task.

        Sends a ``GET`` to ``/v1/query/video_generation``.

        Args:
            task_id: The task identifier returned by :meth:`create`.

        Returns:
            The raw API response dict containing ``status``, and on
            success ``file_id``, ``video_width``, ``video_height``.
        """
        return await self._http.request("GET", _QUERY_PATH, params={"task_id": task_id})

    # ── Private helper ───────────────────────────────────────────────────

    async def _generate(
        self,
        body: dict[str, Any],
        *,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Shared pipeline: create -> poll -> retrieve -> VideoResult.

        Args:
            body: JSON body for the ``POST /v1/video_generation`` request.
            poll_interval: Seconds between status queries.  Falls back to
                the client-level ``poll_interval`` default.
            poll_timeout: Maximum seconds to wait before raising
                :class:`PollTimeoutError`.  Falls back to the client-level
                ``poll_timeout`` default.

        Returns:
            A :class:`VideoResult` with the download URL resolved.
        """
        # 1. Create the generation task.
        create_resp = await self.create(**body)
        task_id: str = create_resp["task_id"]

        # 2. Poll until the task reaches a terminal state.
        interval = poll_interval if poll_interval is not None else self._client.poll_interval
        timeout = poll_timeout if poll_timeout is not None else self._client.poll_timeout

        poll_resp = await async_poll_task(
            self._http,
            _QUERY_PATH,
            task_id,
            poll_interval=interval,
            poll_timeout=timeout,
        )

        # 3. Retrieve the file to obtain a download URL.
        file_id: str = poll_resp["file_id"]
        file_info = await self._client.files.retrieve(file_id)

        return VideoResult(
            task_id=task_id,
            status=poll_resp["status"],
            file_id=file_id,
            download_url=file_info.download_url,
            video_width=poll_resp["video_width"],
            video_height=poll_resp["video_height"],
        )

    # ── High-level ───────────────────────────────────────────────────────

    async def text_to_video(
        self,
        prompt: str,
        model: str = "MiniMax-Hailuo-2.3",
        *,
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        duration: int = 6,
        resolution: str | None = None,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video from a text prompt (T2V).

        Creates a generation task, polls until completion, and resolves
        the file download URL.

        Args:
            prompt: Text description of the desired video content.
            model: Model identifier. Defaults to ``"MiniMax-Hailuo-2.3"``.
            prompt_optimizer: Whether to optimize the prompt server-side.
            fast_pretreatment: Enable fast pre-treatment mode.
            duration: Video duration in seconds (default ``6``).
            resolution: Output resolution (e.g. ``"1280x720"``).
                ``None`` lets the API choose the default.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            fast_pretreatment=fast_pretreatment,
            duration=duration,
            resolution=resolution,
            callback_url=callback_url,
        )
        return await self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    async def image_to_video(
        self,
        first_frame_image: str,
        model: str = "MiniMax-Hailuo-2.3",
        *,
        prompt: str | None = None,
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        duration: int = 6,
        resolution: str | None = None,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video from a first-frame image (I2V).

        Creates a generation task, polls until completion, and resolves
        the file download URL.

        Args:
            first_frame_image: URL or base64 data URI of the first frame.
            model: Model identifier. Defaults to ``"MiniMax-Hailuo-2.3"``.
            prompt: Optional text prompt to guide generation.
            prompt_optimizer: Whether to optimize the prompt server-side.
            fast_pretreatment: Enable fast pre-treatment mode.
            duration: Video duration in seconds (default ``6``).
            resolution: Output resolution (e.g. ``"1280x720"``).
                ``None`` lets the API choose the default.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            fast_pretreatment=fast_pretreatment,
            duration=duration,
            resolution=resolution,
            callback_url=callback_url,
            first_frame_image=first_frame_image,
        )
        return await self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    async def frames_to_video(
        self,
        last_frame_image: str,
        *,
        first_frame_image: str | None = None,
        model: str = "MiniMax-Hailuo-02",
        prompt: str | None = None,
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        duration: int = 6,
        resolution: str | None = None,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video from frame endpoints (FL2V).

        Interpolates between an optional first frame and a required last
        frame to produce a video.

        Args:
            last_frame_image: URL or base64 data URI of the last frame
                (required).
            first_frame_image: URL or base64 data URI of the first frame
                (optional).
            model: Model identifier. Defaults to ``"MiniMax-Hailuo-02"``.
            prompt: Optional text prompt to guide generation.
            prompt_optimizer: Whether to optimize the prompt server-side.
            fast_pretreatment: Enable fast pre-treatment mode.
            duration: Video duration in seconds (default ``6``).
            resolution: Output resolution (e.g. ``"1280x720"``).
                ``None`` lets the API choose the default.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            fast_pretreatment=fast_pretreatment,
            duration=duration,
            resolution=resolution,
            callback_url=callback_url,
            first_frame_image=first_frame_image,
            last_frame_image=last_frame_image,
        )
        return await self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    async def subject_to_video(
        self,
        subject_reference: list[dict[str, Any]],
        *,
        prompt: str | None = None,
        model: str = "S2V-01",
        prompt_optimizer: bool = True,
        callback_url: str | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
    ) -> VideoResult:
        """Generate a video driven by subject references (S2V).

        Uses one or more subject reference images to drive video generation.

        Args:
            subject_reference: List of subject reference dicts, each
                containing ``"type"`` and ``"image"`` keys.
            prompt: Optional text prompt to guide generation.
            model: Model identifier. Defaults to ``"S2V-01"``.
            prompt_optimizer: Whether to optimize the prompt server-side.
            callback_url: Optional webhook URL for completion notification.
            poll_interval: Override client-level polling interval (seconds).
            poll_timeout: Override client-level polling timeout (seconds).

        Returns:
            A :class:`VideoResult` with task metadata and a temporary
            download URL (valid for ~1 hour).
        """
        body = _build_request_body(
            model=model,
            prompt=prompt,
            prompt_optimizer=prompt_optimizer,
            callback_url=callback_url,
            subject_reference=subject_reference,
        )
        return await self._generate(
            body,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )
