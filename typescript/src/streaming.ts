/**
 * SSE (Server-Sent Events) decoder for streaming responses.
 *
 * Handles both Anthropic-format SSE (for text resource) and
 * MiniMax-native SSE (for speech/music streaming).
 */

import { MiniMaxError } from "./error.js";

// ── SSE line parser ─────────────────────────────────────────────────────────

/**
 * Parse a ReadableStream of text lines into SSE data payloads.
 *
 * SSE format:
 *   event: <type>
 *   data: <json>
 *   <empty line>
 */
export async function* parseSSEStream(
  stream: ReadableStream<string>,
): AsyncGenerator<Record<string, unknown>> {
  const reader = stream.getReader();
  let dataBuf = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const line = value;

      if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (data === "[DONE]") return;
        dataBuf += (dataBuf ? "\n" : "") + data;
      } else if (line === "") {
        if (dataBuf) {
          let payload: Record<string, unknown>;
          try {
            payload = JSON.parse(dataBuf) as Record<string, unknown>;
          } catch {
            throw new MiniMaxError(`Malformed SSE data: ${dataBuf}`);
          }
          dataBuf = "";

          const eventType = String(payload.type ?? "");

          if (eventType === "ping") continue;

          if (eventType === "error") {
            const error = (payload.error ?? {}) as Record<string, unknown>;
            throw new MiniMaxError(String(error.message ?? "Stream error"));
          }

          yield payload;
        }
      }
    }

    // Handle trailing event without empty line
    if (dataBuf) {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(dataBuf) as Record<string, unknown>;
      } catch {
        throw new MiniMaxError(`Malformed SSE data: ${dataBuf}`);
      }
      const eventType = String(payload.type ?? "");

      if (eventType === "error") {
        const error = (payload.error ?? {}) as Record<string, unknown>;
        throw new MiniMaxError(String(error.message ?? "Stream error"));
      }

      if (eventType !== "ping") {
        yield payload;
      }
    }
  } finally {
    await reader.cancel();
  }
}

// ── MiniMax native SSE (for speech/music) ───────────────────────────────────

/**
 * Parse MiniMax native SSE lines and extract hex-encoded audio chunks.
 *
 * Format: data: {"data":{"audio":"hex..."}}
 */
export async function* parseNativeSSEAudioChunks(
  stream: ReadableStream<string>,
): AsyncGenerator<Buffer> {
  for await (const payload of parseSSEStream(stream)) {
    const data = (payload.data ?? {}) as Record<string, unknown>;
    const hex = data.audio as string | undefined;
    if (hex) {
      yield Buffer.from(hex, "hex");
    }
  }
}

/**
 * Parse a single SSE data line. Returns the parsed JSON or null.
 */
export function parseSSELine(line: string): Record<string, unknown> | null {
  if (!line.startsWith("data: ")) return null;
  const data = line.slice(6);
  if (data === "[DONE]") return null;
  try {
    return JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
}
