"""Tests for minimax_sdk.exceptions."""

from __future__ import annotations

import pytest

from minimax_sdk.exceptions import (
    ERROR_CODE_MAP,
    RETRYABLE_CODES,
    AuthError,
    ContentSafetyError,
    InsufficientBalanceError,
    InputSafetyError,
    InvalidParameterError,
    MiniMaxError,
    OutputSafetyError,
    PollTimeoutError,
    RateLimitError,
    ServerError,
    APITimeoutError,
    VoiceCloneError,
    VoiceDuplicateError,
    VoiceError,
    VoicePermissionError,
)


# ── ERROR_CODE_MAP completeness ──────────────────────────────────────────────


class TestErrorCodeMap:
    """Verify that ERROR_CODE_MAP covers every documented error code."""

    def test_map_has_23_entries(self) -> None:
        assert len(ERROR_CODE_MAP) == 23

    EXPECTED_MAPPING: dict[int, type[MiniMaxError]] = {
        1000: ServerError,
        1001: APITimeoutError,
        1002: RateLimitError,
        1004: AuthError,
        1008: InsufficientBalanceError,
        1024: ServerError,
        1026: InputSafetyError,
        1027: OutputSafetyError,
        1033: ServerError,
        1039: RateLimitError,
        1041: RateLimitError,
        1042: InvalidParameterError,
        1043: VoiceCloneError,
        1044: VoiceCloneError,
        2013: InvalidParameterError,
        20132: InvalidParameterError,
        2037: InvalidParameterError,
        2039: VoiceDuplicateError,
        2042: VoicePermissionError,
        2045: RateLimitError,
        2048: InvalidParameterError,
        2049: AuthError,
        2056: InsufficientBalanceError,
    }

    @pytest.mark.parametrize(
        "code, expected_cls",
        list(EXPECTED_MAPPING.items()),
        ids=[str(c) for c in EXPECTED_MAPPING],
    )
    def test_code_maps_to_correct_exception(
        self, code: int, expected_cls: type[MiniMaxError]
    ) -> None:
        assert ERROR_CODE_MAP[code] is expected_cls


# ── RETRYABLE_CODES ──────────────────────────────────────────────────────────


class TestRetryableCodes:
    def test_retryable_codes_exact_set(self) -> None:
        assert RETRYABLE_CODES == {1000, 1001, 1002, 1024, 1033}

    def test_retryable_codes_is_set(self) -> None:
        assert isinstance(RETRYABLE_CODES, set)


# ── Exception attributes ─────────────────────────────────────────────────────


class TestExceptionAttributes:
    def test_minimax_error_defaults(self) -> None:
        exc = MiniMaxError()
        assert exc.code == 0
        assert exc.message == "Unknown error"
        assert exc.trace_id == ""

    def test_minimax_error_with_values(self) -> None:
        exc = MiniMaxError(
            "Something went wrong", code=1000, trace_id="abc-123"
        )
        assert exc.code == 1000
        assert exc.message == "Something went wrong"
        assert exc.trace_id == "abc-123"

    def test_str_includes_code_and_trace_id(self) -> None:
        exc = MiniMaxError("Bad request", code=2013, trace_id="t-42")
        text = str(exc)
        assert "[code=2013]" in text
        assert "Bad request" in text
        assert "(trace_id=t-42)" in text

    def test_str_omits_code_when_zero(self) -> None:
        exc = MiniMaxError("oops", code=0, trace_id="")
        text = str(exc)
        assert "[code=" not in text
        assert "trace_id" not in text

    def test_repr_format(self) -> None:
        exc = ServerError("internal", code=1000, trace_id="tr-1")
        r = repr(exc)
        assert "ServerError(" in r
        assert "code=1000" in r
        assert "trace_id='tr-1'" in r

    def test_exception_is_raised_and_caught(self) -> None:
        with pytest.raises(MiniMaxError) as exc_info:
            raise ServerError("fail", code=1000, trace_id="x")
        assert exc_info.value.code == 1000


# ── Inheritance hierarchy ────────────────────────────────────────────────────


class TestInheritanceHierarchy:
    def test_input_safety_is_content_safety(self) -> None:
        exc = InputSafetyError("bad input", code=1026, trace_id="")
        assert isinstance(exc, ContentSafetyError)

    def test_output_safety_is_content_safety(self) -> None:
        exc = OutputSafetyError("bad output", code=1027, trace_id="")
        assert isinstance(exc, ContentSafetyError)

    def test_content_safety_is_minimax_error(self) -> None:
        exc = ContentSafetyError("safety", code=0, trace_id="")
        assert isinstance(exc, MiniMaxError)

    def test_input_safety_is_minimax_error(self) -> None:
        exc = InputSafetyError("bad input", code=1026, trace_id="")
        assert isinstance(exc, MiniMaxError)

    def test_voice_clone_error_is_voice_error(self) -> None:
        exc = VoiceCloneError("clone fail", code=1043, trace_id="")
        assert isinstance(exc, VoiceError)

    def test_voice_duplicate_is_voice_error(self) -> None:
        exc = VoiceDuplicateError("dup", code=2039, trace_id="")
        assert isinstance(exc, VoiceError)

    def test_voice_permission_is_voice_error(self) -> None:
        exc = VoicePermissionError("denied", code=2042, trace_id="")
        assert isinstance(exc, VoiceError)

    def test_voice_error_is_minimax_error(self) -> None:
        exc = VoiceError("voice", code=0, trace_id="")
        assert isinstance(exc, MiniMaxError)

    def test_server_error_is_minimax_error(self) -> None:
        exc = ServerError("server", code=1000, trace_id="")
        assert isinstance(exc, MiniMaxError)

    def test_poll_timeout_is_minimax_error(self) -> None:
        exc = PollTimeoutError("timeout", code=0, trace_id="")
        assert isinstance(exc, MiniMaxError)

    def test_all_exceptions_are_base_exceptions(self) -> None:
        """Every custom exception must ultimately be a Python Exception."""
        for cls in ERROR_CODE_MAP.values():
            assert issubclass(cls, Exception)
