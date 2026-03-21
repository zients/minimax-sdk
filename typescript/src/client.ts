/**
 * Top-level MiniMax client class.
 *
 * Provides access to all MiniMax resources via property namespaces:
 *
 *   const client = new MiniMax({ apiKey: "sk-xxx" });
 *   const result = await client.text.create({ ... });
 *   const audio = await client.speech.tts({ ... });
 */

import { HttpClient, type RequestOptions } from "./http.js";
import { Text } from "./resources/text.js";
import { Speech } from "./resources/speech.js";
import { Voice } from "./resources/voice.js";
import { Video } from "./resources/video.js";
import { Image } from "./resources/image.js";
import { Music } from "./resources/music.js";
import { Files } from "./resources/files.js";

// ── Configuration ───────────────────────────────────────────────────────────

const DEFAULT_BASE_URL = "https://api.minimax.io";
const DEFAULT_TIMEOUT = 600_000; // 600 seconds in ms
const DEFAULT_MAX_RETRIES = 2;
const DEFAULT_POLL_INTERVAL = 5; // seconds
const DEFAULT_POLL_TIMEOUT = 600; // seconds

export interface ClientOptions {
  apiKey?: string;
  baseURL?: string;
  timeout?: number;
  maxRetries?: number;
  pollInterval?: number;
  pollTimeout?: number;
  fetch?: typeof fetch;
}

// ── Client ──────────────────────────────────────────────────────────────────

export class MiniMax {
  readonly text: Text;
  readonly speech: Speech;
  readonly voice: Voice;
  readonly video: Video;
  readonly image: Image;
  readonly music: Music;
  readonly files: Files;

  readonly pollInterval: number;
  readonly pollTimeout: number;

  /** @internal */
  readonly _httpClient: HttpClient;

  constructor(options: ClientOptions = {}) {
    const apiKey =
      options.apiKey ?? process.env.MINIMAX_API_KEY ?? "";
    if (!apiKey) {
      throw new Error(
        "MiniMax API key is required. Provide it via the 'apiKey' option " +
          "or set the MINIMAX_API_KEY environment variable.",
      );
    }

    const baseURL =
      options.baseURL ??
      process.env.MINIMAX_BASE_URL ??
      DEFAULT_BASE_URL;

    this.pollInterval = options.pollInterval ?? DEFAULT_POLL_INTERVAL;
    this.pollTimeout = options.pollTimeout ?? DEFAULT_POLL_TIMEOUT;

    this._httpClient = new HttpClient({
      apiKey,
      baseURL,
      timeout: options.timeout ?? DEFAULT_TIMEOUT,
      maxRetries: options.maxRetries ?? DEFAULT_MAX_RETRIES,
      fetch: options.fetch,
    });

    // Mount resource namespaces
    this.text = new Text(this);
    this.speech = new Speech(this);
    this.voice = new Voice(this);
    this.video = new Video(this);
    this.image = new Image(this);
    this.music = new Music(this);
    this.files = new Files(this);
  }

  // ── HTTP primitives (delegated to HttpClient) ─────────────────────────

  /** @internal */
  request(
    method: string,
    path: string,
    opts?: RequestOptions,
  ): Promise<Record<string, unknown>> {
    return this._httpClient.request(method, path, opts);
  }

  /** @internal */
  requestAnthropic(
    method: string,
    path: string,
    opts?: RequestOptions,
  ): Promise<Record<string, unknown>> {
    return this._httpClient.requestAnthropic(method, path, opts);
  }

  /** @internal */
  streamRequest(
    method: string,
    path: string,
    opts?: RequestOptions,
  ): Promise<ReadableStream<string>> {
    return this._httpClient.streamRequest(method, path, opts);
  }

  /** @internal */
  streamRequestAnthropic(
    method: string,
    path: string,
    opts?: RequestOptions,
  ): Promise<ReadableStream<string>> {
    return this._httpClient.streamRequestAnthropic(method, path, opts);
  }

  /** @internal */
  requestBytes(
    method: string,
    path: string,
    opts?: RequestOptions,
  ): Promise<ArrayBuffer> {
    return this._httpClient.requestBytes(method, path, opts);
  }

  /** @internal */
  upload(
    path: string,
    file: Blob | Buffer,
    filename: string,
    purpose: string,
  ): Promise<Record<string, unknown>> {
    return this._httpClient.upload(path, file, filename, purpose);
  }
}

export default MiniMax;
