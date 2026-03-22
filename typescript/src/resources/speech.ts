/**
 * Speech resource -- synchronous TTS, streaming TTS, and async long-text TTS.
 *
 * Provides the {@link Speech} resource class with methods for all MiniMax
 * text-to-speech endpoints:
 *
 * - {@link Speech.tts} -- one-shot synchronous synthesis
 * - {@link Speech.ttsStream} -- streaming synthesis yielding audio chunks
 * - {@link Speech.asyncCreate} -- create a long-text async task
 * - {@link Speech.asyncQuery} -- query async task status
 * - {@link Speech.asyncGenerate} -- high-level: create + poll + retrieve
 *
 * WebSocket-based real-time TTS (connect method) will be added separately.
 */

import { APIResource } from "../resource.js";
import { AudioResponse, buildAudioResponse, decodeHexAudio } from "../audio.js";
import { MiniMaxError } from "../error.js";
import { raiseForStatus } from "../http.js";
import { pollTask } from "../polling.js";
import { parseNativeSSEAudioChunks } from "../streaming.js";
import type { FileInfo } from "./files.js";

// ── Constants ────────────────────────────────────────────────────────────────

const T2A_PATH = "/v1/t2a_v2";
const T2A_ASYNC_PATH = "/v1/t2a_async_v2";
const T2A_ASYNC_QUERY_PATH = "/v1/query/t2a_async_query_v2";
const WS_T2A_PATH = "/ws/v1/t2a_v2";

// ── Type interfaces ──────────────────────────────────────────────────────────

/** Voice configuration (voiceId, speed, vol, pitch, etc.). */
export interface VoiceSetting {
  voiceId?: string;
  speed?: number;
  vol?: number;
  pitch?: number;
  [key: string]: unknown;
}

/** Audio output configuration (sampleRate, format, etc.). */
export interface AudioSetting {
  sampleRate?: number;
  format?: string;
  bitrate?: number;
  channel?: number;
  [key: string]: unknown;
}

/** Voice modification parameters (pitch, intensity, etc.). */
export interface VoiceModify {
  [key: string]: unknown;
}

/** Custom pronunciation dictionary entries. */
export interface PronunciationDict {
  [key: string]: unknown;
}

/** Timbre blending weight entry for multi-voice synthesis. */
export interface TimbreWeight {
  voiceId: string;
  weight: number;
  [key: string]: unknown;
}

/** Parameters for synchronous and streaming TTS. */
export interface TTSParams {
  /** The text to synthesize. */
  text: string;
  /** The TTS model to use (e.g. "speech-2.8-hd"). */
  model: string;
  /** Voice configuration. */
  voiceSetting?: VoiceSetting;
  /** Audio output configuration. */
  audioSetting?: AudioSetting;
  /** ISO language code to boost recognition for a specific language. */
  languageBoost?: string;
  /** Voice modification parameters. */
  voiceModify?: VoiceModify;
  /** Custom pronunciation dictionary entries. */
  pronunciationDict?: PronunciationDict;
  /** Timbre blending weights for multi-voice synthesis. */
  timbreWeights?: TimbreWeight[];
  /** Whether to include subtitle/timing information. */
  subtitleEnable?: boolean;
  /** Audio encoding in the response (default "hex"). */
  outputFormat?: string;
}

/** Parameters for async long-text TTS creation. */
export interface AsyncCreateParams {
  /** The text to synthesize. Mutually exclusive with textFileId. */
  text?: string;
  /** The TTS model to use (default "speech-2.8-hd"). */
  model?: string;
  /** ID of a previously uploaded text file. Mutually exclusive with text. */
  textFileId?: number;
  /** Voice configuration (required). */
  voiceSetting: VoiceSetting;
  /** Audio output configuration. */
  audioSetting?: AudioSetting;
  /** ISO language code to boost recognition for a specific language. */
  languageBoost?: string;
  /** Voice modification parameters. */
  voiceModify?: VoiceModify;
  /** Custom pronunciation dictionary entries. */
  pronunciationDict?: PronunciationDict;
}

/** Parameters for the high-level asyncGenerate method. */
export interface AsyncGenerateParams extends AsyncCreateParams {
  /** Seconds between status polls (default from client config). */
  pollInterval?: number;
  /** Maximum seconds to wait for completion (default from client config). */
  pollTimeout?: number;
}

/** Final result of a completed async task (create + poll + retrieve). */
export interface TaskResult {
  taskId: string;
  status: string;
  fileId: string;
  downloadUrl: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function convertVoiceSetting(vs: VoiceSetting): Record<string, unknown> {
  const { voiceId, ...rest } = vs;
  const out: Record<string, unknown> = { ...rest };
  if (voiceId !== undefined) out.voice_id = voiceId;
  return out;
}

function convertAudioSetting(as_: AudioSetting): Record<string, unknown> {
  const { sampleRate, ...rest } = as_;
  const out: Record<string, unknown> = { ...rest };
  if (sampleRate !== undefined) out.sample_rate = sampleRate;
  return out;
}

function convertTimbreWeight(tw: TimbreWeight): Record<string, unknown> {
  const { voiceId, ...rest } = tw;
  return { ...rest, voice_id: voiceId };
}

function buildTTSBody(params: TTSParams, stream: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: params.model,
    text: params.text,
    stream,
    output_format: params.outputFormat ?? "hex",
  };
  if (params.voiceSetting !== undefined)
    body.voice_setting = convertVoiceSetting(params.voiceSetting);
  if (params.audioSetting !== undefined)
    body.audio_setting = convertAudioSetting(params.audioSetting);
  if (params.languageBoost !== undefined) body.language_boost = params.languageBoost;
  if (params.voiceModify !== undefined) body.voice_modify = params.voiceModify;
  if (params.pronunciationDict !== undefined) body.pronunciation_dict = params.pronunciationDict;
  if (params.timbreWeights !== undefined)
    body.timbre_weights = params.timbreWeights.map(convertTimbreWeight);
  if (params.subtitleEnable !== undefined) body.subtitle_enable = params.subtitleEnable;
  return body;
}

function buildAsyncBody(params: AsyncCreateParams): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: params.model ?? "speech-2.8-hd",
    voice_setting: convertVoiceSetting(params.voiceSetting),
  };
  if (params.text !== undefined) body.text = params.text;
  if (params.textFileId !== undefined) body.text_file_id = params.textFileId;
  if (params.audioSetting !== undefined)
    body.audio_setting = convertAudioSetting(params.audioSetting);
  if (params.languageBoost !== undefined) body.language_boost = params.languageBoost;
  if (params.voiceModify !== undefined) body.voice_modify = params.voiceModify;
  if (params.pronunciationDict !== undefined) body.pronunciation_dict = params.pronunciationDict;
  return body;
}

// ── Speech resource ──────────────────────────────────────────────────────────

/**
 * Speech synthesis resource.
 *
 * Provides methods for synchronous TTS, streaming TTS, and async long-text
 * TTS via the MiniMax API.
 */
export class Speech extends APIResource {
  // ── Synchronous TTS ──────────────────────────────────────────────────

  /**
   * Synthesize speech from text (synchronous, non-streaming).
   *
   * Sends a `POST /v1/t2a_v2` request with `stream=false` and returns a
   * fully decoded {@link AudioResponse}.
   *
   * @param params - TTS parameters including text, model, and voice settings.
   * @returns The synthesized audio with decoded bytes.
   */
  async tts(params: TTSParams): Promise<AudioResponse> {
    const body = buildTTSBody(params, false);
    const resp = await this._client.request("POST", T2A_PATH, {
      json: body,
    });
    return buildAudioResponse(resp);
  }

  // ── Streaming TTS ────────────────────────────────────────────────────

  /**
   * Synthesize speech from text with streaming output.
   *
   * Sends a `POST /v1/t2a_v2` request with `stream=true` in the body and
   * yields decoded audio bytes (Buffer) as each SSE event arrives.
   *
   * @param params - TTS parameters including text, model, and voice settings.
   * @yields Decoded audio bytes for each streamed chunk.
   *
   * @example
   * ```ts
   * for await (const chunk of client.speech.ttsStream({
   *   text: "Hello, world!",
   *   model: "speech-2.8-hd",
   *   voiceSetting: { voiceId: "male-qn-qingse" },
   * })) {
   *   outputStream.write(chunk);
   * }
   * ```
   */
  async *ttsStream(params: TTSParams): AsyncGenerator<Buffer> {
    const body = buildTTSBody(params, true);
    const stream = await this._client.streamRequest("POST", T2A_PATH, {
      json: body,
    });
    yield* parseNativeSSEAudioChunks(stream);
  }

  // ── WebSocket TTS ──────────────────────────────────────────────────────

  /**
   * Open a WebSocket connection for real-time, multi-turn TTS.
   *
   * Returns a {@link SpeechConnection} that supports sending multiple
   * texts over a single connection. The connection uses the
   * `task_start` / `task_continue` / `task_finish` protocol.
   *
   * Usage:
   * ```typescript
   * const conn = await client.speech.connect({
   *   model: "speech-2.8-hd",
   *   voiceSetting: { voiceId: "English_expressive_narrator" },
   * });
   * try {
   *   const audio = await conn.send("Hello!");
   *   await audio.save("hello.mp3");
   * } finally {
   *   await conn.close();
   * }
   * ```
   */
  async connect(params: {
    model: string;
    voiceSetting: VoiceSetting;
    audioSetting?: AudioSetting;
    languageBoost?: string;
    voiceModify?: VoiceModify;
    pronunciationDict?: PronunciationDict;
    timbreWeights?: TimbreWeight[];
  }): Promise<SpeechConnection> {
    const baseURL = this._client._httpClient.baseURL;
    const parsed = new URL(baseURL);
    const wsURL = `wss://${parsed.host}${WS_T2A_PATH}`;

    const config = buildWSConfig(params);

    const { default: WebSocket } = await import("ws");
    const ws = new WebSocket(wsURL, {
      headers: {
        Authorization: `Bearer ${this._client._httpClient.getApiKey()}`,
      },
    });

    await new Promise<void>((resolve, reject) => {
      const onOpen = () => {
        ws.off("error", onError);
        resolve();
      };
      const onError = (e: Error) => {
        ws.off("open", onOpen);
        reject(e);
      };
      ws.once("open", onOpen);
      ws.once("error", onError);
    });

    const conn = new SpeechConnection(ws, config);
    try {
      await conn._start();
    } catch (err) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      throw err;
    }
    return conn;
  }

  // ── Async TTS (long text) ────────────────────────────────────────────

  /**
   * Create a long-text async TTS task.
   *
   * Sends a `POST /v1/t2a_async_v2` request. Returns the raw response
   * containing `task_id`, `file_id`, and `task_token`.
   *
   * Either `text` or `textFileId` must be provided.
   *
   * @param params - Async TTS parameters including text or textFileId,
   *   model, and voice settings.
   * @returns Raw API response with `task_id`, `file_id`, and `task_token`.
   */
  async asyncCreate(params: AsyncCreateParams): Promise<Record<string, unknown>> {
    const body = buildAsyncBody(params);
    return this._client.request("POST", T2A_ASYNC_PATH, { json: body });
  }

  /**
   * Query the status of an async TTS task.
   *
   * Sends a `GET /v1/query/t2a_async_query_v2?task_id={taskId}`.
   *
   * @param taskId - The task identifier returned by {@link asyncCreate}.
   * @returns Raw API response with `task_id`, `status`, and `file_id`
   *   (when complete).
   */
  async asyncQuery(taskId: string): Promise<Record<string, unknown>> {
    return this._client.request("GET", T2A_ASYNC_QUERY_PATH, {
      params: { task_id: taskId },
    });
  }

  /**
   * Create a long-text TTS task and wait for it to complete.
   *
   * This high-level method combines {@link asyncCreate}, polling via
   * {@link asyncQuery}, and `files.retrieve` into a single call.
   *
   * @param params - Async generation parameters including text or textFileId,
   *   model, voice settings, and optional polling configuration.
   * @returns The completed task result with `downloadUrl`.
   * @throws {PollTimeoutError} If the task does not complete within the
   *   configured timeout.
   * @throws {MiniMaxError} If the task fails.
   */
  async asyncGenerate(params: AsyncGenerateParams): Promise<TaskResult> {
    // Step 1: Create the async task
    const createResp = await this.asyncCreate(params);
    const taskId = String(createResp.task_id ?? "");

    // Step 2: Poll until done
    const interval = params.pollInterval ?? this._client.pollInterval;
    const timeout = params.pollTimeout ?? this._client.pollTimeout;

    const pollResult = await pollTask(this._client._httpClient, T2A_ASYNC_QUERY_PATH, taskId, {
      pollInterval: interval,
      pollTimeout: timeout,
    });

    // Step 3: Retrieve file info for the download URL
    const fileId = String(pollResult.file_id ?? "");
    const fileInfo: FileInfo = await this._client.files.retrieve(fileId);
    const downloadUrl = fileInfo.downloadUrl ?? "";

    return {
      taskId: taskId,
      status: String(pollResult.status ?? "Success"),
      fileId: fileId,
      downloadUrl: downloadUrl,
    };
  }
}

// ── WebSocket helpers ─────────────────────────────────────────────────────

function buildWSConfig(params: {
  model: string;
  voiceSetting: VoiceSetting;
  audioSetting?: AudioSetting;
  languageBoost?: string;
  voiceModify?: VoiceModify;
  pronunciationDict?: PronunciationDict;
  timbreWeights?: TimbreWeight[];
}): Record<string, unknown> {
  const config: Record<string, unknown> = {
    model: params.model,
    voice_setting: convertVoiceSetting(params.voiceSetting),
  };
  if (params.audioSetting !== undefined)
    config.audio_setting = convertAudioSetting(params.audioSetting);
  if (params.languageBoost !== undefined) config.language_boost = params.languageBoost;
  if (params.voiceModify !== undefined) config.voice_modify = params.voiceModify;
  if (params.pronunciationDict !== undefined) config.pronunciation_dict = params.pronunciationDict;
  if (params.timbreWeights !== undefined)
    config.timbre_weights = params.timbreWeights.map(convertTimbreWeight);
  return config;
}

function parseWSMessage(raw: string | Buffer): Record<string, unknown> {
  const text = typeof raw === "string" ? raw : raw.toString("utf-8");
  const msg = JSON.parse(text) as Record<string, unknown>;
  const baseResp = (msg.base_resp ?? {}) as Record<string, unknown>;
  const code = Number(baseResp.status_code ?? 0);
  if (code !== 0) {
    raiseForStatus(msg);
  }
  return msg;
}

function audioResponseFromWSChunks(
  hexChunks: string[],
  extraInfo: Record<string, unknown>,
): AudioResponse {
  const combinedHex = hexChunks.join("");
  const audioBytes = combinedHex ? decodeHexAudio(combinedHex) : Buffer.alloc(0);

  return new AudioResponse({
    data: audioBytes,
    duration: Number(extraInfo.audio_length ?? 0),
    sampleRate: Number(extraInfo.audio_sample_rate ?? 0),
    format: String(extraInfo.audio_format ?? "mp3"),
    size: Number(extraInfo.audio_size ?? 0) || audioBytes.length,
  });
}

// ── SpeechConnection ──────────────────────────────────────────────────────

/**
 * WebSocket connection for real-time TTS.
 *
 * Manages the lifecycle of a single WebSocket session using the
 * `task_start` / `task_continue` / `task_finish` protocol.
 *
 * The WebSocket has a 120-second idle timeout enforced by the server.
 */
export class SpeechConnection {
  private _ws: import("ws").default;
  private _config: Record<string, unknown>;
  private _closed = false;
  sessionId = "";

  /** @internal */
  constructor(ws: import("ws").default, config: Record<string, unknown>) {
    this._ws = ws;
    this._config = config;
  }

  /** @internal Send task_start and wait for task_started. */
  async _start(): Promise<void> {
    const startMsg = { event: "task_start", ...this._config };
    this._ws.send(JSON.stringify(startMsg));

    return new Promise<void>((resolve, reject) => {
      const cleanup = () => {
        this._ws.off("message", handler);
        this._ws.off("close", onClose);
        this._ws.off("error", onError);
      };
      const onClose = () => {
        cleanup();
        reject(new Error("WebSocket closed during task_start"));
      };
      const onError = (err: Error) => {
        cleanup();
        reject(err);
      };
      const handler = (raw: import("ws").RawData) => {
        try {
          const msg = parseWSMessage(raw.toString());
          const event = String(msg.event ?? "");
          if (event === "task_started") {
            this.sessionId = String(msg.session_id ?? "");
            cleanup();
            resolve();
          } else if (event === "task_failed") {
            cleanup();
            const base = (msg.base_resp ?? {}) as Record<string, unknown>;
            reject(
              new MiniMaxError(
                String(msg.message ?? "WebSocket task_start failed"),
                Number(base.status_code ?? 0),
                String(msg.trace_id ?? ""),
              ),
            );
          }
        } catch (err) {
          cleanup();
          reject(err);
        }
      };
      this._ws.on("message", handler);
      this._ws.once("close", onClose);
      this._ws.once("error", onError);
    });
  }

  /**
   * Send text and receive a complete AudioResponse.
   *
   * Sends a `task_continue` event, collects all `task_continued` chunks,
   * and returns a single AudioResponse when `is_final` is received.
   */
  async send(text: string): Promise<AudioResponse> {
    if (this._closed) throw new Error("SpeechConnection is already closed.");

    this._ws.send(JSON.stringify({ event: "task_continue", text }));

    const hexChunks: string[] = [];
    let extraInfo: Record<string, unknown> = {};

    return new Promise<AudioResponse>((resolve, reject) => {
      const cleanup = () => {
        this._ws.off("message", handler);
        this._ws.off("close", onClose);
        this._ws.off("error", onError);
      };
      const onClose = () => {
        cleanup();
        reject(new Error("WebSocket closed unexpectedly"));
      };
      const onError = (err: Error) => {
        cleanup();
        reject(err);
      };
      const handler = (raw: import("ws").RawData) => {
        try {
          const msg = parseWSMessage(raw.toString());
          const event = String(msg.event ?? "");

          if (event === "task_continued") {
            const data = (msg.data ?? {}) as Record<string, unknown>;
            const hex = data.audio as string | undefined;
            if (hex) hexChunks.push(hex);
            if (msg.extra_info) extraInfo = msg.extra_info as Record<string, unknown>;
            if (msg.is_final) {
              cleanup();
              resolve(audioResponseFromWSChunks(hexChunks, extraInfo));
            }
          } else if (event === "task_failed") {
            cleanup();
            const base = (msg.base_resp ?? {}) as Record<string, unknown>;
            reject(
              new MiniMaxError(
                String(msg.message ?? "WebSocket task_continue failed"),
                Number(base.status_code ?? 0),
                String(msg.trace_id ?? ""),
              ),
            );
          }
        } catch (err) {
          cleanup();
          reject(err);
        }
      };
      this._ws.on("message", handler);
      this._ws.once("close", onClose);
      this._ws.once("error", onError);
    });
  }

  /**
   * Send text and yield decoded audio bytes as they arrive.
   */
  async *sendStream(text: string): AsyncGenerator<Buffer> {
    if (this._closed) throw new Error("SpeechConnection is already closed.");

    this._ws.send(JSON.stringify({ event: "task_continue", text }));

    const queue: Array<Buffer | null | Error> = [];
    let resolve: (() => void) | null = null;

    const handler = (raw: import("ws").RawData) => {
      try {
        const msg = parseWSMessage(raw.toString());
        const event = String(msg.event ?? "");

        if (event === "task_continued") {
          const data = (msg.data ?? {}) as Record<string, unknown>;
          const hex = data.audio as string | undefined;
          if (hex) queue.push(decodeHexAudio(hex));
          if (msg.is_final) {
            this._ws.off("message", handler);
            queue.push(null); // signal end
          }
        } else if (event === "task_failed") {
          this._ws.off("message", handler);
          const base = (msg.base_resp ?? {}) as Record<string, unknown>;
          queue.push(
            new MiniMaxError(
              String(msg.message ?? "WebSocket task_continue failed"),
              Number(base.status_code ?? 0),
              String(msg.trace_id ?? ""),
            ),
          );
        }
      } catch (err) {
        this._ws.off("message", handler);
        queue.push(err instanceof Error ? err : new Error(String(err)));
      }
      if (resolve) {
        resolve();
        resolve = null;
      }
    };
    const onClose = () => {
      queue.push(new Error("WebSocket closed unexpectedly"));
      if (resolve) {
        resolve();
        resolve = null;
      }
    };
    const onError = (err: Error) => {
      queue.push(err);
      if (resolve) {
        resolve();
        resolve = null;
      }
    };
    this._ws.on("message", handler);
    this._ws.once("close", onClose);
    this._ws.once("error", onError);

    try {
      while (true) {
        if (queue.length === 0) {
          await new Promise<void>((r) => {
            resolve = r;
          });
        }
        const item = queue.shift();
        if (item === null || item === undefined) return;
        if (item instanceof Error) throw item;
        yield item;
      }
    } finally {
      this._ws.off("message", handler);
      this._ws.off("close", onClose);
      this._ws.off("error", onError);
    }
  }

  /**
   * Send `task_finish` and close the WebSocket connection.
   * Safe to call multiple times.
   */
  async close(): Promise<void> {
    if (this._closed) return;
    this._closed = true;

    try {
      this._ws.send(JSON.stringify({ event: "task_finish" }));
      await new Promise<void>((resolve) => {
        const cleanup = () => {
          clearTimeout(timer);
          this._ws.off("message", handler);
        };
        const handler = (raw: import("ws").RawData) => {
          try {
            const msg = parseWSMessage(raw.toString());
            const event = String(msg.event ?? "");
            if (event === "task_finished" || event === "task_failed") {
              cleanup();
              resolve();
            }
          } catch {
            cleanup();
            resolve();
          }
        };
        this._ws.on("message", handler);
        const timer = setTimeout(() => {
          cleanup();
          resolve();
        }, 5000);
      });
    } catch {
      // Connection already gone
    } finally {
      try {
        this._ws.close();
      } catch {
        // ignore
      }
    }
  }
}
