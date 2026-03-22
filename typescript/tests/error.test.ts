import { describe, it, expect } from "vitest";
import {
  MiniMaxError,
  AuthError,
  RateLimitError,
  InsufficientBalanceError,
  ContentSafetyError,
  InputSafetyError,
  OutputSafetyError,
  InvalidParameterError,
  APITimeoutError,
  PollTimeoutError,
  VoiceError,
  VoiceCloneError,
  VoiceDuplicateError,
  VoicePermissionError,
  ServerError,
  ERROR_CODE_MAP,
  RETRYABLE_CODES,
  ANTHROPIC_ERROR_TYPE_MAP,
} from "../src/error.js";

// ── Error class basics ──────────────────────────────────────────────────────

describe("MiniMaxError", () => {
  it("should set name, code, message, and traceId", () => {
    const err = new MiniMaxError("something went wrong", 42, "trace-1");
    expect(err.name).toBe("MiniMaxError");
    expect(err.message).toBe("something went wrong");
    expect(err.code).toBe(42);
    expect(err.traceId).toBe("trace-1");
  });

  it("should default code to 0 and traceId to empty string", () => {
    const err = new MiniMaxError("fail");
    expect(err.code).toBe(0);
    expect(err.traceId).toBe("");
  });

  it("should be an instance of Error", () => {
    const err = new MiniMaxError("test");
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(MiniMaxError);
  });
});

describe("Error subclasses", () => {
  const classes = [
    { Cls: AuthError, expectedName: "AuthError" },
    { Cls: RateLimitError, expectedName: "RateLimitError" },
    { Cls: InsufficientBalanceError, expectedName: "InsufficientBalanceError" },
    { Cls: ContentSafetyError, expectedName: "ContentSafetyError" },
    { Cls: InputSafetyError, expectedName: "InputSafetyError" },
    { Cls: OutputSafetyError, expectedName: "OutputSafetyError" },
    { Cls: InvalidParameterError, expectedName: "InvalidParameterError" },
    { Cls: APITimeoutError, expectedName: "APITimeoutError" },
    { Cls: PollTimeoutError, expectedName: "PollTimeoutError" },
    { Cls: VoiceError, expectedName: "VoiceError" },
    { Cls: VoiceCloneError, expectedName: "VoiceCloneError" },
    { Cls: VoiceDuplicateError, expectedName: "VoiceDuplicateError" },
    { Cls: VoicePermissionError, expectedName: "VoicePermissionError" },
    { Cls: ServerError, expectedName: "ServerError" },
  ] as const;

  for (const { Cls, expectedName } of classes) {
    it(`${expectedName} should have correct name property`, () => {
      const err = new Cls("msg", 1, "t");
      expect(err.name).toBe(expectedName);
    });

    it(`${expectedName} should extend MiniMaxError`, () => {
      const err = new Cls("msg");
      expect(err).toBeInstanceOf(MiniMaxError);
      expect(err).toBeInstanceOf(Error);
    });
  }

  it("InputSafetyError should extend ContentSafetyError", () => {
    const err = new InputSafetyError("msg");
    expect(err).toBeInstanceOf(ContentSafetyError);
  });

  it("OutputSafetyError should extend ContentSafetyError", () => {
    const err = new OutputSafetyError("msg");
    expect(err).toBeInstanceOf(ContentSafetyError);
  });

  it("VoiceCloneError should extend VoiceError", () => {
    const err = new VoiceCloneError("msg");
    expect(err).toBeInstanceOf(VoiceError);
  });

  it("VoiceDuplicateError should extend VoiceError", () => {
    const err = new VoiceDuplicateError("msg");
    expect(err).toBeInstanceOf(VoiceError);
  });

  it("VoicePermissionError should extend VoiceError", () => {
    const err = new VoicePermissionError("msg");
    expect(err).toBeInstanceOf(VoiceError);
  });
});

// ── ERROR_CODE_MAP ──────────────────────────────────────────────────────────

describe("ERROR_CODE_MAP", () => {
  it("should map 1000 to ServerError", () => {
    expect(ERROR_CODE_MAP[1000]).toBe(ServerError);
  });

  it("should map 1001 to APITimeoutError", () => {
    expect(ERROR_CODE_MAP[1001]).toBe(APITimeoutError);
  });

  it("should map 1002 to RateLimitError", () => {
    expect(ERROR_CODE_MAP[1002]).toBe(RateLimitError);
  });

  it("should map 1004 to AuthError", () => {
    expect(ERROR_CODE_MAP[1004]).toBe(AuthError);
  });

  it("should map 1008 to InsufficientBalanceError", () => {
    expect(ERROR_CODE_MAP[1008]).toBe(InsufficientBalanceError);
  });

  it("should map 1024 to ServerError", () => {
    expect(ERROR_CODE_MAP[1024]).toBe(ServerError);
  });

  it("should map 1026 to InputSafetyError", () => {
    expect(ERROR_CODE_MAP[1026]).toBe(InputSafetyError);
  });

  it("should map 1027 to OutputSafetyError", () => {
    expect(ERROR_CODE_MAP[1027]).toBe(OutputSafetyError);
  });

  it("should map 1033 to ServerError", () => {
    expect(ERROR_CODE_MAP[1033]).toBe(ServerError);
  });

  it("should map 1039 to RateLimitError", () => {
    expect(ERROR_CODE_MAP[1039]).toBe(RateLimitError);
  });

  it("should map 1041 to RateLimitError", () => {
    expect(ERROR_CODE_MAP[1041]).toBe(RateLimitError);
  });

  it("should map 1042 to InvalidParameterError", () => {
    expect(ERROR_CODE_MAP[1042]).toBe(InvalidParameterError);
  });

  it("should map 1043 to VoiceCloneError", () => {
    expect(ERROR_CODE_MAP[1043]).toBe(VoiceCloneError);
  });

  it("should map 1044 to VoiceCloneError", () => {
    expect(ERROR_CODE_MAP[1044]).toBe(VoiceCloneError);
  });

  it("should map 2013 to InvalidParameterError", () => {
    expect(ERROR_CODE_MAP[2013]).toBe(InvalidParameterError);
  });

  it("should map 20132 to InvalidParameterError", () => {
    expect(ERROR_CODE_MAP[20132]).toBe(InvalidParameterError);
  });

  it("should map 2037 to InvalidParameterError", () => {
    expect(ERROR_CODE_MAP[2037]).toBe(InvalidParameterError);
  });

  it("should map 2039 to VoiceDuplicateError", () => {
    expect(ERROR_CODE_MAP[2039]).toBe(VoiceDuplicateError);
  });

  it("should map 2042 to VoicePermissionError", () => {
    expect(ERROR_CODE_MAP[2042]).toBe(VoicePermissionError);
  });

  it("should map 2045 to RateLimitError", () => {
    expect(ERROR_CODE_MAP[2045]).toBe(RateLimitError);
  });

  it("should map 2048 to InvalidParameterError", () => {
    expect(ERROR_CODE_MAP[2048]).toBe(InvalidParameterError);
  });

  it("should map 2049 to AuthError", () => {
    expect(ERROR_CODE_MAP[2049]).toBe(AuthError);
  });

  it("should map 2056 to InsufficientBalanceError", () => {
    expect(ERROR_CODE_MAP[2056]).toBe(InsufficientBalanceError);
  });

  it("should return undefined for unmapped code", () => {
    expect(ERROR_CODE_MAP[9999]).toBeUndefined();
  });
});

// ── RETRYABLE_CODES ─────────────────────────────────────────────────────────

describe("RETRYABLE_CODES", () => {
  it("should contain 1000", () => {
    expect(RETRYABLE_CODES.has(1000)).toBe(true);
  });

  it("should contain 1001", () => {
    expect(RETRYABLE_CODES.has(1001)).toBe(true);
  });

  it("should contain 1002", () => {
    expect(RETRYABLE_CODES.has(1002)).toBe(true);
  });

  it("should contain 1024", () => {
    expect(RETRYABLE_CODES.has(1024)).toBe(true);
  });

  it("should contain 1033", () => {
    expect(RETRYABLE_CODES.has(1033)).toBe(true);
  });

  it("should have exactly 5 entries", () => {
    expect(RETRYABLE_CODES.size).toBe(5);
  });

  it("should not contain non-retryable code 1004", () => {
    expect(RETRYABLE_CODES.has(1004)).toBe(false);
  });
});

// ── ANTHROPIC_ERROR_TYPE_MAP ────────────────────────────────────────────────

describe("ANTHROPIC_ERROR_TYPE_MAP", () => {
  it("should map authentication_error to AuthError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["authentication_error"]).toBe(AuthError);
  });

  it("should map billing_error to InsufficientBalanceError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["billing_error"]).toBe(InsufficientBalanceError);
  });

  it("should map permission_error to AuthError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["permission_error"]).toBe(AuthError);
  });

  it("should map rate_limit_error to RateLimitError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["rate_limit_error"]).toBe(RateLimitError);
  });

  it("should map invalid_request_error to InvalidParameterError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["invalid_request_error"]).toBe(InvalidParameterError);
  });

  it("should map not_found_error to MiniMaxError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["not_found_error"]).toBe(MiniMaxError);
  });

  it("should map request_too_large to InvalidParameterError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["request_too_large"]).toBe(InvalidParameterError);
  });

  it("should map api_error to ServerError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["api_error"]).toBe(ServerError);
  });

  it("should map overloaded_error to ServerError", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["overloaded_error"]).toBe(ServerError);
  });

  it("should return undefined for unmapped type", () => {
    expect(ANTHROPIC_ERROR_TYPE_MAP["nonexistent_type"]).toBeUndefined();
  });
});
