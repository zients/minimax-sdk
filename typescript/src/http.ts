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
import { VERSION } from "./version.js";

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
  const traceId = String(
    body.trace_id ?? (base as Record<string, unknown>).trace_id ?? "",
  );
  return { code, msg, traceId };
}

export function raiseForStatus(body: Record<string, unknown>): void {
  const { code, msg, traceId } = parseError(body);
  if (code === 0) return;
  const Cls = ERROR_CODE_MAP[code] ?? MiniMaxError;
  throw new Cls(msg, code, traceId);
}

export function raiseAnthropicError(
  status: number,
  body: Record<string, unknown>,
): void {
  const error = (body.error ?? {}) as Record<string, unknown>;
  const errorType = String(error.type ?? "api_error");
  const message = String(error.message ?? "Unknown error");
  const requestId = String(body.request_id ?? "");
  const Cls = ANTHROPIC_ERROR_TYPE_MAP[errorType] ?? MiniMaxError;
  throw new Cls(message, status, requestId);
}

// ── Retry helpers ───────────────────────────────────────────────────────────

const DEFAULT_BASE_DELAY = 1.0;
const ANTHROPIC_RETRYABLE_STATUS = new Set([429, 500, 529]);

function backoffDelay(attempt: number, base = DEFAULT_BASE_DELAY): number {
  return base * 2 ** attempt;
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

// ── HTTP Client ─────────────────────────────────────────────────────────────

export class HttpClient {
  readonly baseURL: string;
  readonly maxRetries: number;
  private readonly _apiKey: string;
  private readonly _timeout: number;
  private readonly _fetchFn: typeof fetch;

  constructor(opts: {
    apiKey: string;
    baseURL: string;
    timeout: number;
    maxRetries: number;
    fetch?: typeof fetch;
  }) {
    this._apiKey = opts.apiKey;
    this.baseURL = opts.baseURL.replace(/\/+$/, "");
    this._timeout = opts.timeout;
    this.maxRetries = opts.maxRetries;
    this._fetchFn = opts.fetch ?? globalThis.fetch;
  }

  private _headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this._apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": `minimax-sdk-typescript/${VERSION}`,
    };
  }

  private _buildURL(
    path: string,
    params?: Record<string, string>,
  ): string {
    const url = new URL(path, this.baseURL);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
      }
    }
    return url.toString();
  }

  private _createAbortSignal(
    externalSignal?: AbortSignal,
  ): { signal: AbortSignal; clear: () => void } {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this._timeout);

    if (externalSignal) {
      externalSignal.addEventListener("abort", () => controller.abort());
    }

    return {
      signal: controller.signal,
      clear: () => clearTimeout(timer),
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
        const response = await this._fetchFn(
          this._buildURL(path, opts.params),
          {
            method,
            headers: this._headers(),
            body: opts.json ? JSON.stringify(opts.json) : undefined,
            signal,
          },
        );
        clear();

        const body = (await response.json()) as Record<string, unknown>;
        const { code, msg } = parseError(body);

        if (code === 0) return body;

        if (RETRYABLE_CODES.has(code) && attempt < this.maxRetries) {
          let delay = backoffDelay(attempt);
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
          await sleep(backoffDelay(attempt));
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
        const response = await this._fetchFn(
          this._buildURL(path, opts.params),
          {
            method,
            headers: this._headers(),
            body: opts.json ? JSON.stringify(opts.json) : undefined,
            signal,
          },
        );
        clear();

        if (response.status === 200) {
          return (await response.json()) as Record<string, unknown>;
        }

        // Retryable HTTP status
        if (
          ANTHROPIC_RETRYABLE_STATUS.has(response.status) &&
          attempt < this.maxRetries
        ) {
          let delay = backoffDelay(attempt);
          if (response.status === 429) {
            const ra = retryAfterSeconds(response.headers);
            if (ra != null) delay = ra * 1000;
          }
          await sleep(delay);
          continue;
        }

        // Non-retryable error
        let body: Record<string, unknown>;
        try {
          body = (await response.json()) as Record<string, unknown>;
        } catch {
          throw new MiniMaxError(
            `HTTP ${response.status}: ${await response.text()}`,
            response.status,
          );
        }
        raiseAnthropicError(response.status, body);
      } catch (err) {
        clear();
        if (err instanceof MiniMaxError) throw err;
        lastErr = err as Error;
        if (attempt < this.maxRetries) {
          await sleep(backoffDelay(attempt));
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

    const response = await this._fetchFn(
      this._buildURL(path, opts.params),
      {
        method,
        headers: this._headers(),
        body: opts.json ? JSON.stringify(opts.json) : undefined,
        signal,
      },
    ).catch((err: Error) => {
      clear();
      throw new MiniMaxError(`HTTP transport error: ${err.message}`);
    });

    if (response.status !== 200) {
      clear();
      let body: Record<string, unknown>;
      try {
        body = (await response.json()) as Record<string, unknown>;
      } catch {
        throw new MiniMaxError(
          `HTTP ${response.status}: ${await response.text()}`,
          response.status,
        );
      }
      raiseAnthropicError(response.status, body);
    }

    if (!response.body) {
      clear();
      throw new MiniMaxError("Response body is null");
    }

    // Return a ReadableStream of text lines
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    return new ReadableStream<string>({
      async pull(controller) {
        const { done, value } = await reader.read();
        if (done) {
          // Flush remaining buffer
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

        for (const line of lines) {
          controller.enqueue(line);
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

    const response = await this._fetchFn(
      this._buildURL(path, opts.params),
      {
        method,
        headers: this._headers(),
        body: opts.json ? JSON.stringify(opts.json) : undefined,
        signal,
      },
    ).catch((err: Error) => {
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
      throw new MiniMaxError(
        `HTTP ${response.status}: ${response.statusText}`,
        response.status,
      );
    }

    if (!response.body) {
      clear();
      throw new MiniMaxError("Response body is null");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    return new ReadableStream<string>({
      async pull(controller) {
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

        for (const line of lines) {
          controller.enqueue(line);
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
      const response = await this._fetchFn(
        this._buildURL(path, opts.params),
        {
          method,
          headers: this._headers(),
          body: opts.json ? JSON.stringify(opts.json) : undefined,
          signal,
        },
      );
      clear();

      if (!response.ok) {
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          const body = (await response.json()) as Record<string, unknown>;
          raiseForStatus(body);
        }
        throw new MiniMaxError(
          `HTTP ${response.status}: ${response.statusText}`,
          response.status,
        );
      }

      return response.arrayBuffer();
    } catch (err) {
      clear();
      if (err instanceof MiniMaxError) throw err;
      throw new MiniMaxError(
        `HTTP transport error: ${(err as Error).message}`,
      );
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
    const blob =
      file instanceof Blob ? file : new Blob([file]);
    formData.append("file", blob, filename);
    formData.append("purpose", purpose);

    const { signal, clear } = this._createAbortSignal();

    try {
      const response = await this._fetchFn(
        this._buildURL(path),
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${this._apiKey}`,
            "User-Agent": `minimax-sdk-typescript/${VERSION}`,
          },
          body: formData,
          signal,
        },
      );
      clear();

      const body = (await response.json()) as Record<string, unknown>;
      raiseForStatus(body);
      return body;
    } catch (err) {
      clear();
      if (err instanceof MiniMaxError) throw err;
      throw new MiniMaxError(
        `HTTP transport error: ${(err as Error).message}`,
      );
    }
  }
}
