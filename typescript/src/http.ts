/**
 * HTTP transport utilities for the MiniMax SDK.
 *
 * Provides request helpers with error mapping, retry logic, streaming,
 * and file upload support — all built on top of the global fetch API.
 */

import {
  ANTHROPIC_ERROR_TYPE_MAP,
  ERROR_CODE_MAP,
  MiniMaxError,
  RETRYABLE_CODES,
} from "./error.js";
declare const __SDK_VERSION__: string;

// ── Types ───────────────────────────────────────────────────────────────────

export interface RequestOptions {
  json?: Record<string, unknown>;
  params?: Record<string, string>;
  signal?: AbortSignal;
}

// ── Error parsing ───────────────────────────────────────────────────────────

interface BaseResp {
  status_code?: number;
  status_msg?: string;
  trace_id?: string;
}

export function parseError(body: Record<string, unknown>): {
  code: number;
  msg: string;
  traceId: string;
} {
  const base = (body.base_resp ?? body) as BaseResp;
  const code = Number(base.status_code ?? 0);
  const msg = String(base.status_msg ?? "");
  const traceId = String(body.trace_id ?? (base as Record<string, unknown>).trace_id ?? "");
  return { code, msg, traceId };
}

export function raiseForStatus(body: Record<string, unknown>): void {
  const { code, msg, traceId } = parseError(body);
  if (code === 0) return;
  const Cls = ERROR_CODE_MAP[code] ?? MiniMaxError;
  throw new Cls(msg, code, traceId);
}

export function raiseAnthropicError(status: number, body: Record<string, unknown>): void {
  const error = (body.error ?? {}) as Record<string, unknown>;
  const errorType = String(error.type ?? "api_error");
  const message = String(error.message ?? "Unknown error");
  const requestId = String(body.request_id ?? "");
  const Cls = ANTHROPIC_ERROR_TYPE_MAP[errorType] ?? MiniMaxError;
  throw new Cls(message, status, requestId);
}

// ── Retry helpers ───────────────────────────────────────────────────────────

const DEFAULT_BASE_DELAY_MS = 1000; // 1 second in milliseconds
const ANTHROPIC_RETRYABLE_STATUS = new Set([429, 500, 529]);

function backoffDelayMs(attempt: number, baseMs = DEFAULT_BASE_DELAY_MS): number {
  return baseMs * 2 ** attempt * (0.5 + Math.random());
}

function retryAfterSeconds(headers: Headers): number | null {
  const value = headers.get("retry-after");
  if (value == null) return null;
  const parsed = parseFloat(value);
  return isNaN(parsed) ? null : parsed;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── Helpers for reading error response bodies ───────────────────────────────

async function readErrorBody(
  response: Response,
): Promise<{ body: Record<string, unknown> | null; text: string }> {
  const text = await response.text();
  try {
    return { body: JSON.parse(text) as Record<string, unknown>, text };
  } catch {
    return { body: null, text };
  }
}

// ── HTTP Client ─────────────────────────────────────────────────────────────

export class HttpClient {
  readonly baseURL: string;
  readonly maxRetries: number;
  #apiKey: string;
  private readonly _timeout: number;
  private readonly _fetchFn: typeof fetch;
  private readonly _retryBaseDelayMs: number;

  constructor(opts: {
    apiKey: string;
    baseURL: string;
    timeout: number;
    maxRetries: number;
    fetch?: typeof fetch;
    /** @internal Base delay for retry backoff (ms). Default 1000. */
    retryBaseDelayMs?: number;
  }) {
    this.#apiKey = opts.apiKey;
    this.baseURL = opts.baseURL.replace(/\/+$/, "");
    this._timeout = opts.timeout;
    this.maxRetries = opts.maxRetries;
    this._fetchFn = opts.fetch ?? globalThis.fetch;
    this._retryBaseDelayMs = opts.retryBaseDelayMs ?? DEFAULT_BASE_DELAY_MS;
  }

  /** @internal */
  getApiKey(): string {
    return this.#apiKey;
  }

  private _headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.#apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": `@zients/minimax-sdk-typescript/${__SDK_VERSION__}`,
    };
  }

  // FIX #8: Use string concatenation to preserve base URL path components
  private _buildURL(path: string, params?: Record<string, string>): string {
    const url = new URL(this.baseURL + path);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
      }
    }
    return url.toString();
  }

  // FIX #6: Remove event listener on cleanup to prevent memory leak
  private _createAbortSignal(externalSignal?: AbortSignal): {
    signal: AbortSignal;
    clear: () => void;
  } {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this._timeout);

    const handler = () => controller.abort();
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort();
      } else {
        externalSignal.addEventListener("abort", handler);
      }
    }

    return {
      signal: controller.signal,
      clear: () => {
        clearTimeout(timer);
        if (externalSignal) {
          externalSignal.removeEventListener("abort", handler);
        }
      },
    };
  }

  // ── Core MiniMax request ────────────────────────────────────────────

  async request(
    method: string,
    path: string,
    opts: RequestOptions = {},
  ): Promise<Record<string, unknown>> {
    let lastErr: Error | null = null;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      const { signal, clear } = this._createAbortSignal(opts.signal);

      try {
        const response = await this._fetchFn(this._buildURL(path, opts.params), {
          method,
          headers: this._headers(),
          body: opts.json ? JSON.stringify(opts.json) : undefined,
          signal,
        });
        clear();

        const body = (await response.json()) as Record<string, unknown>;
        const { code } = parseError(body);

        if (code === 0) return body;

        // FIX #3: backoffDelayMs returns milliseconds directly
        if (RETRYABLE_CODES.has(code) && attempt < this.maxRetries) {
          let delay = backoffDelayMs(attempt, this._retryBaseDelayMs);
          if (code === 1002) {
            const ra = retryAfterSeconds(response.headers);
            if (ra != null) delay = ra * 1000;
          }
          await sleep(delay);
          continue;
        }

        raiseForStatus(body);
      } catch (err) {
        clear();
        if (err instanceof MiniMaxError) throw err;
        lastErr = err as Error;
        if (attempt < this.maxRetries) {
          await sleep(backoffDelayMs(attempt, this._retryBaseDelayMs));
          continue;
        }
        throw new MiniMaxError(`HTTP transport error: ${lastErr.message}`);
      }
    }

    throw new MiniMaxError("Request failed with unknown error");
  }

  // ── Anthropic-compatible request ────────────────────────────────────

  async requestAnthropic(
    method: string,
    path: string,
    opts: RequestOptions = {},
  ): Promise<Record<string, unknown>> {
    let lastErr: Error | null = null;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      const { signal, clear } = this._createAbortSignal(opts.signal);

      try {
        const response = await this._fetchFn(this._buildURL(path, opts.params), {
          method,
          headers: this._headers(),
          body: opts.json ? JSON.stringify(opts.json) : undefined,
          signal,
        });
        clear();

        if (response.status === 200) {
          return (await response.json()) as Record<string, unknown>;
        }

        // Retryable HTTP status
        if (ANTHROPIC_RETRYABLE_STATUS.has(response.status) && attempt < this.maxRetries) {
          let delay = backoffDelayMs(attempt, this._retryBaseDelayMs);
          if (response.status === 429) {
            const ra = retryAfterSeconds(response.headers);
            if (ra != null) delay = ra * 1000;
          }
          await sleep(delay);
          continue;
        }

        // FIX #1: Read body as text first, then try JSON parse (avoid double-consume)
        const { body, text } = await readErrorBody(response);
        if (body) {
          raiseAnthropicError(response.status, body);
        }
        throw new MiniMaxError(`HTTP ${response.status}: ${text}`, response.status);
      } catch (err) {
        clear();
        if (err instanceof MiniMaxError) throw err;
        lastErr = err as Error;
        if (attempt < this.maxRetries) {
          await sleep(backoffDelayMs(attempt, this._retryBaseDelayMs));
          continue;
        }
        throw new MiniMaxError(`HTTP transport error: ${lastErr.message}`);
      }
    }

    throw new MiniMaxError("Request failed with unknown error");
  }

  // ── Anthropic streaming request ─────────────────────────────────────

  async streamRequestAnthropic(
    method: string,
    path: string,
    opts: RequestOptions = {},
  ): Promise<ReadableStream<string>> {
    const { signal, clear } = this._createAbortSignal(opts.signal);

    const response = await this._fetchFn(this._buildURL(path, opts.params), {
      method,
      headers: this._headers(),
      body: opts.json ? JSON.stringify(opts.json) : undefined,
      signal,
    }).catch((err: Error) => {
      clear();
      throw new MiniMaxError(`HTTP transport error: ${err.message}`);
    });

    if (response.status !== 200) {
      clear();
      // FIX #1: Read as text first, then try JSON parse
      const { body, text } = await readErrorBody(response);
      if (body) {
        raiseAnthropicError(response.status, body);
      }
      throw new MiniMaxError(`HTTP ${response.status}: ${text}`, response.status);
    }

    if (!response.body) {
      clear();
      throw new MiniMaxError("Response body is null");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // FIX #7: Add try/catch in pull() for proper cleanup on stream errors
    return new ReadableStream<string>({
      async pull(controller) {
        try {
          // Keep reading until at least one line is enqueued or stream ends.
          // Raw chunks may not contain \n, so a single read() may not
          // produce any complete lines.
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              if (buffer.length > 0) {
                controller.enqueue(buffer);
                buffer = "";
              }
              clear();
              controller.close();
              return;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            if (lines.length > 0) {
              for (const line of lines) {
                controller.enqueue(line.replace(/\r$/, ""));
              }
              return;
            }
          }
        } catch (err) {
          clear();
          controller.error(new MiniMaxError(`Stream error: ${(err as Error).message}`));
        }
      },
      cancel() {
        clear();
        reader.cancel();
      },
    });
  }

  // ── MiniMax native streaming ────────────────────────────────────────

  async streamRequest(
    method: string,
    path: string,
    opts: RequestOptions = {},
  ): Promise<ReadableStream<string>> {
    const { signal, clear } = this._createAbortSignal(opts.signal);

    const response = await this._fetchFn(this._buildURL(path, opts.params), {
      method,
      headers: this._headers(),
      body: opts.json ? JSON.stringify(opts.json) : undefined,
      signal,
    }).catch((err: Error) => {
      clear();
      throw new MiniMaxError(`HTTP transport error: ${err.message}`);
    });

    if (!response.ok) {
      clear();
      const contentType = response.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        const body = (await response.json()) as Record<string, unknown>;
        raiseForStatus(body);
      }
      throw new MiniMaxError(`HTTP ${response.status}: ${response.statusText}`, response.status);
    }

    // Check for JSON error response disguised as 200 OK (e.g. insufficient balance).
    // The API may return 200 with application/json instead of text/event-stream.
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json") && !contentType.includes("text/event-stream")) {
      clear();
      const body = (await response.json()) as Record<string, unknown>;
      raiseForStatus(body);
    }

    if (!response.body) {
      clear();
      throw new MiniMaxError("Response body is null");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // FIX #7: Add try/catch in pull()
    return new ReadableStream<string>({
      async pull(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              if (buffer.length > 0) {
                controller.enqueue(buffer);
                buffer = "";
              }
              clear();
              controller.close();
              return;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            if (lines.length > 0) {
              for (const line of lines) {
                controller.enqueue(line.replace(/\r$/, ""));
              }
              return;
            }
          }
        } catch (err) {
          clear();
          controller.error(new MiniMaxError(`Stream error: ${(err as Error).message}`));
        }
      },
      cancel() {
        clear();
        reader.cancel();
      },
    });
  }

  // ── Raw bytes request ───────────────────────────────────────────────

  async requestBytes(
    method: string,
    path: string,
    opts: RequestOptions = {},
  ): Promise<ArrayBuffer> {
    const { signal, clear } = this._createAbortSignal(opts.signal);

    try {
      const response = await this._fetchFn(this._buildURL(path, opts.params), {
        method,
        headers: this._headers(),
        body: opts.json ? JSON.stringify(opts.json) : undefined,
        signal,
      });
      clear();

      if (!response.ok) {
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          const body = (await response.json()) as Record<string, unknown>;
          raiseForStatus(body);
        }
        throw new MiniMaxError(`HTTP ${response.status}: ${response.statusText}`, response.status);
      }

      return response.arrayBuffer();
    } catch (err) {
      clear();
      if (err instanceof MiniMaxError) throw err;
      throw new MiniMaxError(`HTTP transport error: ${(err as Error).message}`);
    }
  }

  // ── File upload ─────────────────────────────────────────────────────

  async upload(
    path: string,
    file: Blob | Buffer,
    filename: string,
    purpose: string,
  ): Promise<Record<string, unknown>> {
    const formData = new FormData();
    const blob = file instanceof Blob ? file : new Blob([new Uint8Array(file)]);
    formData.append("file", blob, filename);
    formData.append("purpose", purpose);

    const { signal, clear } = this._createAbortSignal();

    try {
      const response = await this._fetchFn(this._buildURL(path), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.#apiKey}`,
          "User-Agent": `@zients/minimax-sdk-typescript/${__SDK_VERSION__}`,
        },
        body: formData,
        signal,
      });
      clear();

      const body = (await response.json()) as Record<string, unknown>;
      raiseForStatus(body);
      return body;
    } catch (err) {
      clear();
      if (err instanceof MiniMaxError) throw err;
      throw new MiniMaxError(`HTTP transport error: ${(err as Error).message}`);
    }
  }
}
