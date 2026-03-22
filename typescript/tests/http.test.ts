import { describe, it, expect, vi, beforeEach } from "vitest";
import { parseError, raiseForStatus, raiseAnthropicError, HttpClient } from "../src/http.js";
import {
  MiniMaxError,
  AuthError,
  RateLimitError,
  ServerError,
  InvalidParameterError,
  InsufficientBalanceError,
} from "../src/error.js";

// ── parseError ──────────────────────────────────────────────────────────────

describe("parseError", () => {
  it("should extract code, msg, and traceId from base_resp", () => {
    const body = {
      base_resp: {
        status_code: 1004,
        status_msg: "auth failed",
      },
      trace_id: "tid-123",
    };
    const result = parseError(body);
    expect(result.code).toBe(1004);
    expect(result.msg).toBe("auth failed");
    expect(result.traceId).toBe("tid-123");
  });

  it("should extract from flat body when base_resp is absent", () => {
    const body = {
      status_code: 1002,
      status_msg: "rate limited",
      trace_id: "tid-456",
    };
    const result = parseError(body);
    expect(result.code).toBe(1002);
    expect(result.msg).toBe("rate limited");
    expect(result.traceId).toBe("tid-456");
  });

  it("should default code to 0 when missing", () => {
    const result = parseError({});
    expect(result.code).toBe(0);
    expect(result.msg).toBe("");
    expect(result.traceId).toBe("");
  });

  it("should use trace_id from base_resp when not at top level", () => {
    const body = {
      base_resp: {
        status_code: 1000,
        status_msg: "server error",
        trace_id: "inner-tid",
      },
    };
    const result = parseError(body);
    expect(result.traceId).toBe("inner-tid");
  });

  it("should prefer top-level trace_id over base_resp trace_id", () => {
    const body = {
      base_resp: {
        status_code: 1000,
        status_msg: "err",
        trace_id: "inner",
      },
      trace_id: "outer",
    };
    const result = parseError(body);
    expect(result.traceId).toBe("outer");
  });
});

// ── raiseForStatus ──────────────────────────────────────────────────────────

describe("raiseForStatus", () => {
  it("should not throw when code is 0", () => {
    expect(() => raiseForStatus({ base_resp: { status_code: 0 } })).not.toThrow();
  });

  it("should throw AuthError for code 1004", () => {
    expect(() =>
      raiseForStatus({
        base_resp: { status_code: 1004, status_msg: "bad key" },
        trace_id: "t",
      }),
    ).toThrow(AuthError);
  });

  it("should throw ServerError for code 1000", () => {
    expect(() =>
      raiseForStatus({
        base_resp: { status_code: 1000, status_msg: "server" },
      }),
    ).toThrow(ServerError);
  });

  it("should throw RateLimitError for code 1002", () => {
    expect(() =>
      raiseForStatus({
        base_resp: { status_code: 1002, status_msg: "rate" },
      }),
    ).toThrow(RateLimitError);
  });

  it("should throw MiniMaxError for unmapped code", () => {
    expect(() =>
      raiseForStatus({
        base_resp: { status_code: 9999, status_msg: "unknown" },
      }),
    ).toThrow(MiniMaxError);
  });

  it("should propagate message and code in thrown error", () => {
    try {
      raiseForStatus({
        base_resp: { status_code: 1004, status_msg: "invalid api key" },
        trace_id: "trace-abc",
      });
      expect.unreachable("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(AuthError);
      const authErr = err as AuthError;
      expect(authErr.message).toBe("invalid api key");
      expect(authErr.code).toBe(1004);
      expect(authErr.traceId).toBe("trace-abc");
    }
  });
});

// ── raiseAnthropicError ─────────────────────────────────────────────────────

describe("raiseAnthropicError", () => {
  it("should throw AuthError for authentication_error type", () => {
    expect(() =>
      raiseAnthropicError(401, {
        error: { type: "authentication_error", message: "bad key" },
        request_id: "req-1",
      }),
    ).toThrow(AuthError);
  });

  it("should throw RateLimitError for rate_limit_error type", () => {
    expect(() =>
      raiseAnthropicError(429, {
        error: { type: "rate_limit_error", message: "slow down" },
      }),
    ).toThrow(RateLimitError);
  });

  it("should throw InvalidParameterError for invalid_request_error", () => {
    expect(() =>
      raiseAnthropicError(400, {
        error: { type: "invalid_request_error", message: "bad request" },
      }),
    ).toThrow(InvalidParameterError);
  });

  it("should throw ServerError for api_error type", () => {
    expect(() =>
      raiseAnthropicError(500, {
        error: { type: "api_error", message: "internal" },
      }),
    ).toThrow(ServerError);
  });

  it("should throw InsufficientBalanceError for billing_error type", () => {
    expect(() =>
      raiseAnthropicError(402, {
        error: { type: "billing_error", message: "no funds" },
      }),
    ).toThrow(InsufficientBalanceError);
  });

  it("should default to MiniMaxError for unknown error type", () => {
    expect(() =>
      raiseAnthropicError(500, {
        error: { type: "unknown_type", message: "wtf" },
      }),
    ).toThrow(MiniMaxError);
  });

  it("should default to api_error type when error.type is missing", () => {
    expect(() => raiseAnthropicError(500, { error: {} })).toThrow(ServerError);
  });

  it("should use status as error code and request_id as traceId", () => {
    try {
      raiseAnthropicError(403, {
        error: { type: "permission_error", message: "no access" },
        request_id: "req-xyz",
      });
      expect.unreachable("should have thrown");
    } catch (err) {
      const e = err as AuthError;
      expect(e.code).toBe(403);
      expect(e.traceId).toBe("req-xyz");
      expect(e.message).toBe("no access");
    }
  });
});

// ── HttpClient helpers ──────────────────────────────────────────────────────

function createMockFetch(
  status: number,
  body: unknown,
  headers?: Record<string, string>,
): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
    headers: new Headers(headers ?? {}),
  });
}

function makeClient(fetchFn: ReturnType<typeof vi.fn>, maxRetries = 2): HttpClient {
  return new HttpClient({
    apiKey: "test-key",
    baseURL: "https://api.example.com",
    timeout: 30_000,
    maxRetries,
    fetch: fetchFn as unknown as typeof fetch,
    retryBaseDelayMs: 0,
  });
}

// ── _createAbortSignal ───────────────────────────────────────────────────────

describe("HttpClient abort signal handling", () => {
  it("should forward non-aborted external signal to fetch", async () => {
    const body = { base_resp: { status_code: 0 }, data: "ok" };
    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: () => Promise.resolve(body),
      headers: new Headers(),
    });
    const client = makeClient(mockFetch, 0);

    const ac = new AbortController();
    // Pass a non-aborted signal — exercises the addEventListener branch
    const result = await client.request("GET", "/v1/test", { signal: ac.signal });
    expect(result).toEqual(body);
  });

  it("should reject immediately when signal is already aborted", async () => {
    // Use a fetch mock that respects the abort signal, like real fetch does
    const abortAwareFetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.signal?.aborted) {
        return Promise.reject(new DOMException("The operation was aborted.", "AbortError"));
      }
      return Promise.resolve({
        status: 200,
        ok: true,
        json: () => Promise.resolve({ base_resp: { status_code: 0 } }),
        headers: new Headers(),
      });
    });
    const client = makeClient(abortAwareFetch, 0);

    const ac = new AbortController();
    ac.abort();

    await expect(client.request("GET", "/v1/test", { signal: ac.signal })).rejects.toThrow();
  });
});

// ── HttpClient.request() ────────────────────────────────────────────────────

describe("HttpClient.request()", () => {
  it("should return body on success (status_code 0)", async () => {
    const body = { base_resp: { status_code: 0 }, data: "hello" };
    const mockFetch = createMockFetch(200, body);
    const client = makeClient(mockFetch);

    const result = await client.request("POST", "/v1/test", {
      json: { prompt: "hi" },
    });
    expect(result).toEqual(body);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("should pass query params correctly", async () => {
    const body = { base_resp: { status_code: 0 } };
    const mockFetch = createMockFetch(200, body);
    const client = makeClient(mockFetch);

    await client.request("GET", "/v1/query", { params: { task_id: "abc" } });

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("task_id=abc");
  });

  it("should retry on retryable code and eventually succeed", async () => {
    const failBody = {
      base_resp: { status_code: 1000, status_msg: "server error" },
    };
    const successBody = { base_resp: { status_code: 0 }, result: "ok" };

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(failBody),
        headers: new Headers(),
      })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(successBody),
        headers: new Headers(),
      });

    const client = makeClient(mockFetch, 2);
    const result = await client.request("POST", "/v1/test");
    expect(result).toEqual(successBody);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should throw on non-retryable error code immediately", async () => {
    const body = {
      base_resp: { status_code: 1004, status_msg: "auth error" },
      trace_id: "t1",
    };
    const mockFetch = createMockFetch(200, body);
    const client = makeClient(mockFetch, 2);

    await expect(client.request("POST", "/v1/test")).rejects.toThrow(AuthError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("should throw after exhausting retries on retryable code", async () => {
    const failBody = {
      base_resp: { status_code: 1000, status_msg: "server down" },
    };
    const mockFetch = createMockFetch(200, failBody);
    const client = makeClient(mockFetch, 1);

    await expect(client.request("POST", "/v1/test")).rejects.toThrow(ServerError);
    // attempt 0 retries, then attempt 1 retries, then attempt 1 (last) raises
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should retry on fetch transport error and eventually succeed", async () => {
    const successBody = { base_resp: { status_code: 0 }, ok: true };
    const mockFetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("ECONNRESET"))
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(successBody),
        headers: new Headers(),
      });

    const client = makeClient(mockFetch, 1);
    const result = await client.request("POST", "/v1/test");
    expect(result).toEqual(successBody);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should throw MiniMaxError after exhausting retries on transport error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("network down"));
    const client = makeClient(mockFetch, 1);

    await expect(client.request("POST", "/v1/test")).rejects.toThrow(MiniMaxError);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should re-throw MiniMaxError immediately without retrying", async () => {
    // A non-retryable MiniMaxError code that causes raiseForStatus to throw
    const body = {
      base_resp: { status_code: 1042, status_msg: "invalid param" },
    };
    const mockFetch = createMockFetch(200, body);
    const client = makeClient(mockFetch, 2);

    await expect(client.request("POST", "/v1/test")).rejects.toThrow(InvalidParameterError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("should handle rate limit code 1002 with retry-after header", async () => {
    const rateLimitBody = {
      base_resp: { status_code: 1002, status_msg: "rate limited" },
    };
    const successBody = { base_resp: { status_code: 0 } };

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(rateLimitBody),
        headers: new Headers({ "retry-after": "0.01" }),
      })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(successBody),
        headers: new Headers(),
      });

    const client = makeClient(mockFetch, 1);
    const result = await client.request("POST", "/v1/test");
    expect(result).toEqual(successBody);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

// ── HttpClient.requestAnthropic() ───────────────────────────────────────────

describe("HttpClient.requestAnthropic()", () => {
  it("should return body on 200 status", async () => {
    const body = { id: "msg_1", content: [] };
    const mockFetch = createMockFetch(200, body);
    const client = makeClient(mockFetch);

    const result = await client.requestAnthropic("POST", "/v1/messages", {
      json: { model: "test" },
    });
    expect(result).toEqual(body);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("should retry on 429 status and eventually succeed", async () => {
    const successBody = { id: "msg_2" };

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        status: 429,
        ok: false,
        json: () =>
          Promise.resolve({
            error: { type: "rate_limit_error", message: "slow" },
          }),
        headers: new Headers({ "retry-after": "0.001" }),
      })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(successBody),
        headers: new Headers(),
      });

    const client = makeClient(mockFetch, 1);
    const result = await client.requestAnthropic("POST", "/v1/messages");
    expect(result).toEqual(successBody);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should retry on 500 status", async () => {
    const successBody = { id: "msg_3" };

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        status: 500,
        ok: false,
        json: () => Promise.resolve({ error: { type: "api_error", message: "err" } }),
        headers: new Headers(),
      })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(successBody),
        headers: new Headers(),
      });

    const client = makeClient(mockFetch, 1);
    const result = await client.requestAnthropic("POST", "/v1/messages");
    expect(result).toEqual(successBody);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should retry on 529 status", async () => {
    const successBody = { id: "msg_4" };

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        status: 529,
        ok: false,
        json: () =>
          Promise.resolve({
            error: { type: "overloaded_error", message: "busy" },
          }),
        headers: new Headers(),
      })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: () => Promise.resolve(successBody),
        headers: new Headers(),
      });

    const client = makeClient(mockFetch, 1);
    const result = await client.requestAnthropic("POST", "/v1/messages");
    expect(result).toEqual(successBody);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should throw AuthError on 401 without retrying", async () => {
    const body = {
      error: { type: "authentication_error", message: "bad api key" },
      request_id: "req-1",
    };
    const mockFetch = createMockFetch(401, body);
    const client = makeClient(mockFetch, 2);

    await expect(client.requestAnthropic("POST", "/v1/messages")).rejects.toThrow(AuthError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("should throw InvalidParameterError on 400", async () => {
    const body = {
      error: { type: "invalid_request_error", message: "missing field" },
    };
    const mockFetch = createMockFetch(400, body);
    const client = makeClient(mockFetch, 2);

    await expect(client.requestAnthropic("POST", "/v1/messages")).rejects.toThrow(
      InvalidParameterError,
    );
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("should throw after exhausting retries on retryable status", async () => {
    const errorBody = {
      error: { type: "rate_limit_error", message: "too many" },
    };

    const mockFetch = vi.fn().mockResolvedValue({
      status: 429,
      ok: false,
      text: () => Promise.resolve(JSON.stringify(errorBody)),
      headers: new Headers(),
    });

    const client = makeClient(mockFetch, 1);
    await expect(client.requestAnthropic("POST", "/v1/messages")).rejects.toThrow(RateLimitError);
    // attempt 0 + 1 retry = 2 calls
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should throw MiniMaxError on transport error after retries", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("timeout"));
    const client = makeClient(mockFetch, 1);

    await expect(client.requestAnthropic("POST", "/v1/messages")).rejects.toThrow(MiniMaxError);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("should handle non-JSON error response body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      status: 502,
      ok: false,
      json: () => Promise.reject(new Error("not json")),
      text: () => Promise.resolve("Bad Gateway"),
      headers: new Headers(),
    });
    const client = makeClient(mockFetch, 0);

    await expect(client.requestAnthropic("POST", "/v1/messages")).rejects.toThrow(MiniMaxError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

// ── HttpClient constructor ──────────────────────────────────────────────────

describe("HttpClient constructor", () => {
  it("should trim trailing slashes from baseURL", () => {
    const client = new HttpClient({
      apiKey: "k",
      baseURL: "https://api.example.com///",
      timeout: 1000,
      maxRetries: 0,
    });
    expect(client.baseURL).toBe("https://api.example.com");
  });

  it("should store maxRetries", () => {
    const client = new HttpClient({
      apiKey: "k",
      baseURL: "https://api.example.com",
      timeout: 1000,
      maxRetries: 5,
    });
    expect(client.maxRetries).toBe(5);
  });

  it("should return the api key via getApiKey()", () => {
    const client = new HttpClient({
      apiKey: "test-secret",
      baseURL: "https://api.example.com",
      timeout: 1000,
      maxRetries: 0,
    });
    expect(client.getApiKey()).toBe("test-secret");
  });
});

// ── streamRequestAnthropic ──────────────────────────────────────────────────

describe("HttpClient.streamRequestAnthropic", () => {
  function makeClient(fetchFn: typeof fetch) {
    return new HttpClient({
      apiKey: "k",
      baseURL: "https://api.example.com",
      timeout: 60000,
      maxRetries: 0,
      fetch: fetchFn,
    });
  }

  it("should return ReadableStream of lines on success", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("line1\nline2\n"));
        controller.close();
      },
    });
    const mockFetch = vi.fn().mockResolvedValue({ status: 200, body });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequestAnthropic("POST", "/test");
    const reader = stream.getReader();
    const chunks: string[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    expect(chunks).toContain("line1");
    expect(chunks).toContain("line2");
  });

  it("should throw on HTTP error with JSON body", async () => {
    const errorBody = { error: { type: "authentication_error", message: "Bad key" } };
    const mockFetch = vi.fn().mockResolvedValue({
      status: 401,
      text: async () => JSON.stringify(errorBody),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequestAnthropic("POST", "/test")).rejects.toThrow(AuthError);
  });

  it("should throw on HTTP error with non-JSON body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      status: 502,
      text: async () => "Bad Gateway",
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequestAnthropic("POST", "/test")).rejects.toThrow(/HTTP 502/);
  });

  it("should throw on null response body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ status: 200, body: null });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequestAnthropic("POST", "/test")).rejects.toThrow(
      "Response body is null",
    );
  });

  it("should throw on fetch error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("network fail"));
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequestAnthropic("POST", "/test")).rejects.toThrow(/transport error/);
  });

  it("should handle stream read error in pull()", async () => {
    // Create a stream whose underlying reader.read() rejects
    let readCount = 0;
    const mockReader = {
      read: vi.fn().mockImplementation(() => {
        readCount++;
        if (readCount === 1) {
          return Promise.resolve({
            done: false,
            value: new TextEncoder().encode("line1\n"),
          });
        }
        return Promise.reject(new Error("stream read failed"));
      }),
      cancel: vi.fn(),
    };
    const mockBody = { getReader: () => mockReader };

    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      body: mockBody,
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequestAnthropic("POST", "/test");
    const reader = stream.getReader();

    // First read succeeds with enqueued data
    await reader.read();
    // Second read should get the MiniMaxError from the catch block
    await expect(reader.read()).rejects.toThrow(/Stream error/);
  });

  it("should flush remaining buffer when stream ends with partial line", async () => {
    const body = new ReadableStream({
      start(controller) {
        // Send data without trailing newline so buffer has leftover
        controller.enqueue(new TextEncoder().encode("line1\npartial"));
        controller.close();
      },
    });
    const mockFetch = vi.fn().mockResolvedValue({ status: 200, body });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequestAnthropic("POST", "/test");
    const reader = stream.getReader();
    const chunks: string[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    expect(chunks).toContain("line1");
    expect(chunks).toContain("partial");
  });

  it("should call reader.cancel() on stream cancel", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: test\n"));
      },
      pull() {
        // Keep stream open
        return new Promise(() => {});
      },
    });
    const mockFetch = vi.fn().mockResolvedValue({ status: 200, body });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequestAnthropic("POST", "/test");
    const reader = stream.getReader();
    // Read first chunk
    await reader.read();
    // Cancel the stream
    await reader.cancel();
  });
});

// ── streamRequest ───────────────────────────────────────────────────────────

describe("HttpClient.streamRequest", () => {
  function makeClient(fetchFn: typeof fetch) {
    return new HttpClient({
      apiKey: "k",
      baseURL: "https://api.example.com",
      timeout: 60000,
      maxRetries: 0,
      fetch: fetchFn,
    });
  }

  it("should return ReadableStream of lines on success", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: hello\n"));
        controller.close();
      },
    });
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body,
      headers: new Headers(),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequest("POST", "/test");
    const reader = stream.getReader();
    const chunks: string[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    expect(chunks).toContain("data: hello");
  });

  it("should throw on HTTP error with JSON content-type", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        base_resp: { status_code: 1000, status_msg: "server error" },
      }),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequest("POST", "/test")).rejects.toThrow(ServerError);
  });

  it("should throw on HTTP error without JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      headers: new Headers({ "content-type": "text/html" }),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequest("POST", "/test")).rejects.toThrow(/HTTP 502/);
  });

  it("should throw on null response body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: null,
      headers: new Headers(),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequest("POST", "/test")).rejects.toThrow("Response body is null");
  });

  it("should throw on fetch error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("fail"));
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.streamRequest("POST", "/test")).rejects.toThrow(/transport error/);
  });

  it("should handle stream read error in pull()", async () => {
    let readCount = 0;
    const mockReader = {
      read: vi.fn().mockImplementation(() => {
        readCount++;
        if (readCount === 1) {
          return Promise.resolve({
            done: false,
            value: new TextEncoder().encode("data: hello\n"),
          });
        }
        return Promise.reject(new Error("stream read failed"));
      }),
      cancel: vi.fn(),
    };
    const mockBody = { getReader: () => mockReader };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body: mockBody,
      headers: new Headers(),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequest("POST", "/test");
    const reader = stream.getReader();

    // First read succeeds
    await reader.read();
    // Next read should get the error
    await expect(reader.read()).rejects.toThrow(/Stream error/);
  });

  it("should flush remaining buffer when stream ends with partial line", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("line1\npartial"));
        controller.close();
      },
    });
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body,
      headers: new Headers(),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequest("POST", "/test");
    const reader = stream.getReader();
    const chunks: string[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    expect(chunks).toContain("line1");
    expect(chunks).toContain("partial");
  });

  it("should call reader.cancel() on stream cancel", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: test\n"));
      },
      pull() {
        return new Promise(() => {});
      },
    });
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      body,
      headers: new Headers(),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const stream = await client.streamRequest("POST", "/test");
    const reader = stream.getReader();
    await reader.read();
    await reader.cancel();
  });
});

// ── requestBytes ────────────────────────────────────────────────────────────

describe("HttpClient.requestBytes", () => {
  function makeClient(fetchFn: typeof fetch) {
    return new HttpClient({
      apiKey: "k",
      baseURL: "https://api.example.com",
      timeout: 60000,
      maxRetries: 0,
      fetch: fetchFn,
    });
  }

  it("should return ArrayBuffer on success", async () => {
    const data = new Uint8Array([1, 2, 3]).buffer;
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => data,
      headers: new Headers(),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const result = await client.requestBytes("GET", "/test");
    expect(result).toBe(data);
  });

  it("should throw on HTTP error with JSON body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        base_resp: { status_code: 2013, status_msg: "param error" },
      }),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.requestBytes("GET", "/test")).rejects.toThrow(InvalidParameterError);
  });

  it("should throw on HTTP error without JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      headers: new Headers({ "content-type": "text/plain" }),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.requestBytes("GET", "/test")).rejects.toThrow(/HTTP 500/);
  });

  it("should throw on fetch error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("network"));
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(client.requestBytes("GET", "/test")).rejects.toThrow(/transport error/);
  });
});

// ── upload ───────────────────────────────────────────────────────────────────

describe("HttpClient.upload", () => {
  function makeClient(fetchFn: typeof fetch) {
    return new HttpClient({
      apiKey: "k",
      baseURL: "https://api.example.com",
      timeout: 60000,
      maxRetries: 0,
      fetch: fetchFn,
    });
  }

  it("should upload file and return body", async () => {
    const respBody = {
      base_resp: { status_code: 0, status_msg: "" },
      file: { file_id: "123" },
    };
    const mockFetch = vi.fn().mockResolvedValue({
      json: async () => respBody,
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    const result = await client.upload(
      "/v1/files/upload",
      Buffer.from("audio"),
      "test.mp3",
      "voice_clone",
    );

    expect(result.file).toEqual({ file_id: "123" });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockFetch.mock.calls[0]!;
    expect(url).toContain("/v1/files/upload");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBeInstanceOf(FormData);
  });

  it("should throw on API error", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: async () => ({
        base_resp: { status_code: 1004, status_msg: "auth failed" },
      }),
    });
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(
      client.upload("/v1/files/upload", Buffer.from("x"), "f.mp3", "voice_clone"),
    ).rejects.toThrow(AuthError);
  });

  it("should throw on fetch error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("fail"));
    const client = makeClient(mockFetch as unknown as typeof fetch);

    await expect(
      client.upload("/v1/files/upload", Buffer.from("x"), "f.mp3", "voice_clone"),
    ).rejects.toThrow(/transport error/);
  });
});
