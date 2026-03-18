"""MiniMax SDK exception hierarchy.

All exceptions carry:
- code: int — original MiniMax status_code
- message: str — original status_msg
- trace_id: str — for debugging
"""

from __future__ import annotations


class MiniMaxError(Exception):
    """Base exception for all MiniMax SDK errors."""

    def __init__(
        self,
        message: str = "Unknown error",
        *,
        code: int = 0,
        trace_id: str = "",
    ) -> None:
        self.code = code
        self.message = message
        self.trace_id = trace_id
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(code={self.code}, "
            f"message={self.message!r}, trace_id={self.trace_id!r})"
        )

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.insert(0, f"[code={self.code}]")
        if self.trace_id:
            parts.append(f"(trace_id={self.trace_id})")
        return " ".join(parts)


# ── Auth ──────────────────────────────────────────────────────────────────────


class AuthError(MiniMaxError):
    """Authentication failed (codes 1004, 2049)."""


# ── Rate Limiting ─────────────────────────────────────────────────────────────


class RateLimitError(MiniMaxError):
    """Rate limit exceeded (codes 1002, 1039, 1041, 2045)."""


# ── Balance ───────────────────────────────────────────────────────────────────


class InsufficientBalanceError(MiniMaxError):
    """Insufficient balance or usage limit exceeded (codes 1008, 2056)."""


# ── Content Safety ────────────────────────────────────────────────────────────


class ContentSafetyError(MiniMaxError):
    """Content safety violation (codes 1026, 1027)."""


class InputSafetyError(ContentSafetyError):
    """Input content triggered safety filter (code 1026)."""


class OutputSafetyError(ContentSafetyError):
    """Output content triggered safety filter (code 1027)."""


# ── Invalid Parameters ────────────────────────────────────────────────────────


class InvalidParameterError(MiniMaxError):
    """Invalid request parameters (codes 2013, 20132, 1042, 2037, 2048)."""


# ── Timeouts ──────────────────────────────────────────────────────────────────


class APITimeoutError(MiniMaxError):
    """Request timed out on the server side (code 1001)."""


class PollTimeoutError(MiniMaxError):
    """SDK-side polling timeout — the async task did not complete in time."""


# ── Voice ─────────────────────────────────────────────────────────────────────


class VoiceError(MiniMaxError):
    """Base class for voice-related errors."""


class VoiceCloneError(VoiceError):
    """Voice cloning failed (codes 1043, 1044)."""


class VoiceDuplicateError(VoiceError):
    """Duplicate voice clone attempt (code 2039)."""


class VoicePermissionError(VoiceError):
    """Voice access denied (code 2042)."""


# ── Server ────────────────────────────────────────────────────────────────────


class ServerError(MiniMaxError):
    """Server-side error, typically retryable (codes 1000, 1024, 1033)."""


# ── Error Code Map ────────────────────────────────────────────────────────────

ERROR_CODE_MAP: dict[int, type[MiniMaxError]] = {
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

# Codes that should trigger automatic retry with exponential backoff.
RETRYABLE_CODES: set[int] = {1000, 1001, 1002, 1024, 1033}
