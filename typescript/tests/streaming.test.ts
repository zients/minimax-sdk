import { describe, it, expect } from "vitest";
import { parseSSEStream, parseSSELine } from "../src/streaming.js";
import { MiniMaxError } from "../src/error.js";

// ── Helper: create a ReadableStream from an array of lines ──────────────────

function streamFromLines(lines: string[]): ReadableStream<string> {
  let index = 0;
  return new ReadableStream<string>({
    pull(controller) {
      if (index < lines.length) {
        controller.enqueue(lines[index]!);
        index++;
      } else {
        controller.close();
      }
    },
  });
}

// ── parseSSEStream ──────────────────────────────────────────────────────────

describe("parseSSEStream", () => {
  it("should yield parsed payloads for data events", async () => {
    const stream = streamFromLines([
      'data: {"type":"content_block_delta","delta":{"text":"hi"}}',
      "",
      'data: {"type":"content_block_delta","delta":{"text":" there"}}',
      "",
    ]);

    const results: Record<string, unknown>[] = [];
    for await (const payload of parseSSEStream(stream)) {
      results.push(payload);
    }

    expect(results).toHaveLength(2);
    expect(results[0]).toEqual({
      type: "content_block_delta",
      delta: { text: "hi" },
    });
    expect(results[1]).toEqual({
      type: "content_block_delta",
      delta: { text: " there" },
    });
  });

  it("should skip ping events", async () => {
    const stream = streamFromLines([
      'data: {"type":"ping"}',
      "",
      'data: {"type":"content_block_delta","delta":{"text":"hello"}}',
      "",
    ]);

    const results: Record<string, unknown>[] = [];
    for await (const payload of parseSSEStream(stream)) {
      results.push(payload);
    }

    expect(results).toHaveLength(1);
    expect(results[0]).toEqual({
      type: "content_block_delta",
      delta: { text: "hello" },
    });
  });

  it("should throw MiniMaxError on error events", async () => {
    const stream = streamFromLines(['data: {"type":"error","error":{"message":"overloaded"}}', ""]);

    await expect(async () => {
      for await (const _ of parseSSEStream(stream)) {
        // should not reach here
      }
    }).rejects.toThrow(MiniMaxError);

    // Verify the error message
    const stream2 = streamFromLines([
      'data: {"type":"error","error":{"message":"overloaded"}}',
      "",
    ]);

    try {
      for await (const _ of parseSSEStream(stream2)) {
        // intentionally empty
      }
      expect.unreachable("should have thrown");
    } catch (err) {
      expect((err as MiniMaxError).message).toBe("overloaded");
    }
  });

  it("should throw with default message when error has no message", async () => {
    const stream = streamFromLines(['data: {"type":"error","error":{}}', ""]);

    try {
      for await (const _ of parseSSEStream(stream)) {
        // intentionally empty
      }
      expect.unreachable("should have thrown");
    } catch (err) {
      expect((err as MiniMaxError).message).toBe("Stream error");
    }
  });

  it("should handle trailing data without empty line", async () => {
    const stream = streamFromLines([
      'data: {"type":"message_stop"}',
      // No empty line follows — EOF
    ]);

    const results: Record<string, unknown>[] = [];
    for await (const payload of parseSSEStream(stream)) {
      results.push(payload);
    }

    expect(results).toHaveLength(1);
    expect(results[0]).toEqual({ type: "message_stop" });
  });

  it("should skip trailing ping without empty line", async () => {
    const stream = streamFromLines(['data: {"type":"ping"}']);

    const results: Record<string, unknown>[] = [];
    for await (const payload of parseSSEStream(stream)) {
      results.push(payload);
    }

    expect(results).toHaveLength(0);
  });

  it("should throw on trailing error without empty line", async () => {
    const stream = streamFromLines(['data: {"type":"error","error":{"message":"boom"}}']);

    try {
      for await (const _ of parseSSEStream(stream)) {
        // intentionally empty
      }
      expect.unreachable("should have thrown");
    } catch (err) {
      expect((err as MiniMaxError).message).toBe("boom");
    }
  });

  it("should throw MiniMaxError on malformed JSON data", async () => {
    const stream = streamFromLines(["data: {not valid json}", ""]);

    await expect(async () => {
      for await (const _ of parseSSEStream(stream)) {
        // should not reach here
      }
    }).rejects.toThrow(MiniMaxError);

    // Verify the error message includes the malformed data
    const stream2 = streamFromLines(["data: {not valid json}", ""]);

    try {
      for await (const _ of parseSSEStream(stream2)) {
        // intentionally empty
      }
      expect.unreachable("should have thrown");
    } catch (err) {
      expect((err as MiniMaxError).message).toBe("Malformed SSE data: {not valid json}");
    }
  });

  it("should throw MiniMaxError on trailing malformed JSON without empty line", async () => {
    const stream = streamFromLines([
      "data: {not valid json}",
      // No empty line follows — EOF
    ]);

    try {
      for await (const _ of parseSSEStream(stream)) {
        // intentionally empty
      }
      expect.unreachable("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(MiniMaxError);
      expect((err as MiniMaxError).message).toBe("Malformed SSE data: {not valid json}");
    }
  });

  it("should handle empty stream", async () => {
    const stream = streamFromLines([]);

    const results: Record<string, unknown>[] = [];
    for await (const payload of parseSSEStream(stream)) {
      results.push(payload);
    }

    expect(results).toHaveLength(0);
  });

  it("should ignore non-data lines", async () => {
    const stream = streamFromLines([
      "event: message",
      'data: {"type":"message_start","message":{"id":"msg1"}}',
      "",
      "id: 123",
      ": comment",
    ]);

    const results: Record<string, unknown>[] = [];
    for await (const payload of parseSSEStream(stream)) {
      results.push(payload);
    }

    expect(results).toHaveLength(1);
    expect(results[0]).toEqual({
      type: "message_start",
      message: { id: "msg1" },
    });
  });

  it("should yield multiple events in sequence", async () => {
    const stream = streamFromLines([
      'data: {"type":"message_start","message":{"id":"m1"}}',
      "",
      'data: {"type":"content_block_start","index":0}',
      "",
      'data: {"type":"content_block_delta","delta":{"text":"A"}}',
      "",
      'data: {"type":"content_block_stop","index":0}',
      "",
      'data: {"type":"message_stop"}',
      "",
    ]);

    const results: Record<string, unknown>[] = [];
    for await (const payload of parseSSEStream(stream)) {
      results.push(payload);
    }

    expect(results).toHaveLength(5);
    expect(results.map((r) => r.type)).toEqual([
      "message_start",
      "content_block_start",
      "content_block_delta",
      "content_block_stop",
      "message_stop",
    ]);
  });
});

// ── parseSSELine ────────────────────────────────────────────────────────────

describe("parseSSELine", () => {
  it("should parse a valid data line", () => {
    const result = parseSSELine('data: {"key":"value"}');
    expect(result).toEqual({ key: "value" });
  });

  it("should return null for non-data lines", () => {
    expect(parseSSELine("event: message")).toBeNull();
    expect(parseSSELine("id: 123")).toBeNull();
    expect(parseSSELine(": comment")).toBeNull();
    expect(parseSSELine("")).toBeNull();
    expect(parseSSELine("random text")).toBeNull();
  });

  it("should return null for [DONE] sentinel", () => {
    expect(parseSSELine("data: [DONE]")).toBeNull();
  });

  it("should return null for invalid JSON", () => {
    expect(parseSSELine("data: {invalid json}")).toBeNull();
  });

  it("should parse nested JSON objects", () => {
    const result = parseSSELine('data: {"delta":{"type":"text","text":"hello"},"index":0}');
    expect(result).toEqual({
      delta: { type: "text", text: "hello" },
      index: 0,
    });
  });

  it("should parse JSON with array values", () => {
    const result = parseSSELine('data: {"items":[1,2,3]}');
    expect(result).toEqual({ items: [1, 2, 3] });
  });
});
