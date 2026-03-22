/**
 * MiniMax SDK exception hierarchy.
 *
 * All errors carry:
 * - code: original MiniMax status_code or HTTP status
 * - message: human-readable error description
 * - traceId: request trace identifier for debugging
 */

export class MiniMaxError extends Error {
  readonly code: number;
  readonly traceId: string;

  constructor(message: string, code = 0, traceId = "") {
    super(message);
    this.name = "MiniMaxError";
    this.code = code;
    this.traceId = traceId;
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export class AuthError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "AuthError";
  }
}

// ── Rate Limiting ─────────────────────────────────────────────────────────────

export class RateLimitError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "RateLimitError";
  }
}

// ── Balance ───────────────────────────────────────────────────────────────────

export class InsufficientBalanceError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "InsufficientBalanceError";
  }
}

// ── Content Safety ────────────────────────────────────────────────────────────

export class ContentSafetyError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "ContentSafetyError";
  }
}

export class InputSafetyError extends ContentSafetyError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "InputSafetyError";
  }
}

export class OutputSafetyError extends ContentSafetyError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "OutputSafetyError";
  }
}

// ── Invalid Parameters ──────────────────────────────────────────────────────

export class InvalidParameterError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "InvalidParameterError";
  }
}

// ── Timeouts ────────────────────────────────────────────────────────────────

export class APITimeoutError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "APITimeoutError";
  }
}

export class PollTimeoutError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "PollTimeoutError";
  }
}

// ── Voice ───────────────────────────────────────────────────────────────────

export class VoiceError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "VoiceError";
  }
}

export class VoiceCloneError extends VoiceError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "VoiceCloneError";
  }
}

export class VoiceDuplicateError extends VoiceError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "VoiceDuplicateError";
  }
}

export class VoicePermissionError extends VoiceError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "VoicePermissionError";
  }
}

// ── Server ──────────────────────────────────────────────────────────────────

export class ServerError extends MiniMaxError {
  constructor(message: string, code = 0, traceId = "") {
    super(message, code, traceId);
    this.name = "ServerError";
  }
}

// ── Error Code Mapping ──────────────────────────────────────────────────────

type ErrorConstructor = new (message: string, code: number, traceId: string) => MiniMaxError;

export const ERROR_CODE_MAP: Record<number, ErrorConstructor> = {
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
};

export const RETRYABLE_CODES = new Set([1000, 1001, 1002, 1024, 1033]);

// ── Anthropic-compatible error mapping ──────────────────────────────────────

export const ANTHROPIC_ERROR_TYPE_MAP: Record<string, ErrorConstructor> = {
  authentication_error: AuthError,
  billing_error: InsufficientBalanceError,
  permission_error: AuthError,
  rate_limit_error: RateLimitError,
  invalid_request_error: InvalidParameterError,
  not_found_error: MiniMaxError,
  request_too_large: InvalidParameterError,
  api_error: ServerError,
  overloaded_error: ServerError,
};
