"""Voice resource -- clone, design, list, and delete voices.

Provides both synchronous (:class:`Voice`) and asynchronous (:class:`AsyncVoice`)
clients for MiniMax's voice management APIs.
"""

from __future__ import annotations

from typing import Any, BinaryIO, Union

from .._audio import AudioResponse, build_audio_response, decode_hex_audio
from .._base import AsyncResource, SyncResource
from ..types.files import FileInfo
from ..types.voice import (
    VoiceCloneResult,
    VoiceDesignResult,
    VoiceInfo,
    VoiceList,
)

# Rebuild models that reference AudioResponse via TYPE_CHECKING guard,
# so Pydantic can resolve the forward reference at runtime.
VoiceCloneResult.model_rebuild()
VoiceDesignResult.model_rebuild()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_clone_body(
    file_id: str,
    voice_id: str,
    *,
    clone_prompt: dict[str, Any] | None = None,
    text: str | None = None,
    model: str | None = None,
    language_boost: str | None = None,
    need_noise_reduction: bool = False,
    need_volume_normalization: bool = False,
) -> dict[str, Any]:
    """Assemble the request body for ``POST /v1/voice_clone``.

    Only includes keys whose values are not ``None``.  The boolean flags
    default to ``False`` and are always included in the body so the API
    receives an explicit value.
    """
    body: dict[str, Any] = {
        "file_id": int(file_id),
        "voice_id": voice_id,
        "need_noise_reduction": need_noise_reduction,
        "need_volume_normalization": need_volume_normalization,
    }
    if clone_prompt is not None:
        body["clone_prompt"] = clone_prompt
    if text is not None:
        body["text"] = text
    if model is not None:
        body["model"] = model
    if language_boost is not None:
        body["language_boost"] = language_boost
    return body


def _parse_clone_result(resp: dict[str, Any], voice_id: str) -> VoiceCloneResult:
    """Parse the raw API response into a :class:`VoiceCloneResult`.

    If the response includes ``demo_audio`` (present when *text* and *model*
    were supplied in the request), it is decoded into an
    :class:`AudioResponse`.
    """
    # demo_audio is a URL string when text+model are provided, otherwise empty ""
    demo_audio_url = resp.get("demo_audio", "")

    return VoiceCloneResult(
        voice_id=voice_id,
        demo_audio=demo_audio_url if demo_audio_url else None,
        input_sensitive=resp.get("input_sensitive"),
    )


def _parse_design_result(resp: dict[str, Any]) -> VoiceDesignResult:
    """Parse the raw API response into a :class:`VoiceDesignResult`.

    The ``trial_audio`` is returned as a hex-encoded string by the API.
    """
    raw_trial = resp.get("trial_audio", "")
    trial_audio: AudioResponse | None = None
    if raw_trial:
        if isinstance(raw_trial, str):
            # API returns trial_audio as a hex-encoded string
            audio_bytes = decode_hex_audio(raw_trial)
            trial_audio = AudioResponse(
                data=audio_bytes,
                duration=0,
                sample_rate=0,
                format="mp3",
                size=len(audio_bytes),
            )
        else:
            # Nested dict structure (fallback)
            trial_audio = build_audio_response(raw_trial)

    return VoiceDesignResult(
        voice_id=resp["voice_id"],
        trial_audio=trial_audio,
    )


def _parse_voice_list(resp: dict[str, Any]) -> VoiceList:
    """Parse the raw API response into a :class:`VoiceList`."""
    return VoiceList(
        system_voice=[
            VoiceInfo.model_validate(v) for v in (resp.get("system_voice") or [])
        ],
        voice_cloning=[
            VoiceInfo.model_validate(v) for v in (resp.get("voice_cloning") or [])
        ],
        voice_generation=[
            VoiceInfo.model_validate(v) for v in (resp.get("voice_generation") or [])
        ],
    )


# ── Sync ─────────────────────────────────────────────────────────────────────


class Voice(SyncResource):
    """Synchronous voice resource for cloning, designing, listing, and deleting voices."""

    def upload_audio(
        self,
        file: Union[str, BinaryIO],
        purpose: str = "voice_clone",
    ) -> FileInfo:
        """Upload an audio file for voice cloning or as a prompt audio reference.

        This is a convenience method that delegates to
        :meth:`client.files.upload <minimax_sdk.resources.files.Files.upload>`.

        Args:
            file: A filesystem path (``str``) or an already-opened binary
                file object.
            purpose: The intended use of the file.  Must be ``"voice_clone"``
                (default) or ``"prompt_audio"``.

        Returns:
            A :class:`FileInfo` describing the uploaded file.
        """
        return self._client.files.upload(file, purpose)

    def clone(
        self,
        file_id: str,
        voice_id: str,
        *,
        clone_prompt: dict[str, Any] | None = None,
        text: str | None = None,
        model: str | None = None,
        language_boost: str | None = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
    ) -> VoiceCloneResult:
        """Clone a voice from a previously uploaded audio file.

        Args:
            file_id: The identifier of the uploaded audio file to clone from.
            voice_id: The desired voice identifier for the cloned voice.
            clone_prompt: Optional prompt audio reference dict with keys
                ``"prompt_audio"`` (file ID) and ``"prompt_text"``.
            text: Optional text to generate a demo audio clip with the
                cloned voice.  Requires *model* to be set as well.
            model: TTS model to use for generating the demo audio (e.g.
                ``"speech-2.8-hd"``).  Required when *text* is provided.
            language_boost: Optional language code to boost recognition
                accuracy (e.g. ``"en"``, ``"zh"``).
            need_noise_reduction: Whether to apply noise reduction to the
                source audio before cloning.
            need_volume_normalization: Whether to normalize volume of the
                source audio before cloning.

        Returns:
            A :class:`VoiceCloneResult` containing the ``voice_id`` and,
            when *text*/*model* are provided, a ``demo_audio``
            :class:`AudioResponse`.
        """
        body = _build_clone_body(
            file_id,
            voice_id,
            clone_prompt=clone_prompt,
            text=text,
            model=model,
            language_boost=language_boost,
            need_noise_reduction=need_noise_reduction,
            need_volume_normalization=need_volume_normalization,
        )
        resp = self._http.request("POST", "/v1/voice_clone", json=body)
        return _parse_clone_result(resp, voice_id)

    def design(
        self,
        prompt: str,
        preview_text: str,
        *,
        voice_id: str | None = None,
    ) -> VoiceDesignResult:
        """Design a new voice from a natural-language description.

        Args:
            prompt: A description of the desired voice characteristics
                (e.g. ``"warm female narrator with a British accent"``).
            preview_text: Text to synthesise as a trial audio clip so you
                can hear the designed voice.
            voice_id: Optional identifier to assign to the designed voice.
                If not provided, the API generates one.

        Returns:
            A :class:`VoiceDesignResult` containing the ``voice_id`` and a
            ``trial_audio`` :class:`AudioResponse`.
        """
        body: dict[str, Any] = {
            "prompt": prompt,
            "preview_text": preview_text,
        }
        if voice_id is not None:
            body["voice_id"] = voice_id

        resp = self._http.request("POST", "/v1/voice_design", json=body)
        return _parse_design_result(resp)

    def list(self, voice_type: str = "all") -> VoiceList:
        """List available voices.

        Args:
            voice_type: Filter by type.  One of ``"system"``,
                ``"voice_cloning"``, ``"voice_generation"``, or ``"all"``
                (default).

        Returns:
            A :class:`VoiceList` with separate lists for system, cloned,
            and generated voices (populated according to *voice_type*).
        """
        resp = self._http.request("POST", "/v1/get_voice", json={"voice_type": voice_type})
        return _parse_voice_list(resp)

    def delete(self, voice_id: str, voice_type: str) -> None:
        """Delete a voice.

        Args:
            voice_id: The identifier of the voice to delete.
            voice_type: The type of voice being deleted — ``"voice_cloning"``
                or ``"voice_generation"``.
        """
        self._http.request(
            "POST",
            "/v1/delete_voice",
            json={"voice_id": voice_id, "voice_type": voice_type},
        )


# ── Async ────────────────────────────────────────────────────────────────────


class AsyncVoice(AsyncResource):
    """Asynchronous voice resource for cloning, designing, listing, and deleting voices."""

    async def upload_audio(
        self,
        file: Union[str, BinaryIO],
        purpose: str = "voice_clone",
    ) -> FileInfo:
        """Upload an audio file for voice cloning or as a prompt audio reference.

        This is a convenience method that delegates to
        :meth:`client.files.upload <minimax_sdk.resources.files.AsyncFiles.upload>`.

        Args:
            file: A filesystem path (``str``) or an already-opened binary
                file object.
            purpose: The intended use of the file.  Must be ``"voice_clone"``
                (default) or ``"prompt_audio"``.

        Returns:
            A :class:`FileInfo` describing the uploaded file.
        """
        return await self._client.files.upload(file, purpose)

    async def clone(
        self,
        file_id: str,
        voice_id: str,
        *,
        clone_prompt: dict[str, Any] | None = None,
        text: str | None = None,
        model: str | None = None,
        language_boost: str | None = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
    ) -> VoiceCloneResult:
        """Clone a voice from a previously uploaded audio file.

        Args:
            file_id: The identifier of the uploaded audio file to clone from.
            voice_id: The desired voice identifier for the cloned voice.
            clone_prompt: Optional prompt audio reference dict with keys
                ``"prompt_audio"`` (file ID) and ``"prompt_text"``.
            text: Optional text to generate a demo audio clip with the
                cloned voice.  Requires *model* to be set as well.
            model: TTS model to use for generating the demo audio (e.g.
                ``"speech-2.8-hd"``).  Required when *text* is provided.
            language_boost: Optional language code to boost recognition
                accuracy (e.g. ``"en"``, ``"zh"``).
            need_noise_reduction: Whether to apply noise reduction to the
                source audio before cloning.
            need_volume_normalization: Whether to normalize volume of the
                source audio before cloning.

        Returns:
            A :class:`VoiceCloneResult` containing the ``voice_id`` and,
            when *text*/*model* are provided, a ``demo_audio``
            :class:`AudioResponse`.
        """
        body = _build_clone_body(
            file_id,
            voice_id,
            clone_prompt=clone_prompt,
            text=text,
            model=model,
            language_boost=language_boost,
            need_noise_reduction=need_noise_reduction,
            need_volume_normalization=need_volume_normalization,
        )
        resp = await self._http.request("POST", "/v1/voice_clone", json=body)
        return _parse_clone_result(resp, voice_id)

    async def design(
        self,
        prompt: str,
        preview_text: str,
        *,
        voice_id: str | None = None,
    ) -> VoiceDesignResult:
        """Design a new voice from a natural-language description.

        Args:
            prompt: A description of the desired voice characteristics
                (e.g. ``"warm female narrator with a British accent"``).
            preview_text: Text to synthesise as a trial audio clip so you
                can hear the designed voice.
            voice_id: Optional identifier to assign to the designed voice.
                If not provided, the API generates one.

        Returns:
            A :class:`VoiceDesignResult` containing the ``voice_id`` and a
            ``trial_audio`` :class:`AudioResponse`.
        """
        body: dict[str, Any] = {
            "prompt": prompt,
            "preview_text": preview_text,
        }
        if voice_id is not None:
            body["voice_id"] = voice_id

        resp = await self._http.request("POST", "/v1/voice_design", json=body)
        return _parse_design_result(resp)

    async def list(self, voice_type: str = "all") -> VoiceList:
        """List available voices.

        Args:
            voice_type: Filter by type.  One of ``"system"``,
                ``"voice_cloning"``, ``"voice_generation"``, or ``"all"``
                (default).

        Returns:
            A :class:`VoiceList` with separate lists for system, cloned,
            and generated voices (populated according to *voice_type*).
        """
        resp = await self._http.request("POST", "/v1/get_voice", json={"voice_type": voice_type})
        return _parse_voice_list(resp)

    async def delete(self, voice_id: str, voice_type: str) -> None:
        """Delete a voice.

        Args:
            voice_id: The identifier of the voice to delete.
            voice_type: The type of voice being deleted — ``"voice_cloning"``
                or ``"voice_generation"``.
        """
        await self._http.request(
            "POST",
            "/v1/delete_voice",
            json={"voice_id": voice_id, "voice_type": voice_type},
        )
