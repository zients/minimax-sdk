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
import { AudioResponse, buildAudioResponse } from "../audio.js";
import { pollTask } from "../polling.js";
import { parseNativeSSEAudioChunks } from "../streaming.js";
import type { FileInfo } from "./files.js";

// ── Constants ────────────────────────────────────────────────────────────────

const T2A_PATH = "/v1/t2a_v2";
const T2A_ASYNC_PATH = "/v1/t2a_async_v2";
const T2A_ASYNC_QUERY_PATH = "/v1/query/t2a_async_query_v2";

// ── Type interfaces ──────────────────────────────────────────────────────────

/** Voice configuration (voice_id, speed, vol, pitch, etc.). */
export interface VoiceSetting {
  voice_id?: string;
  speed?: number;
  vol?: number;
  pitch?: number;
  [key: string]: unknown;
}

/** Audio output configuration (sample_rate, format, etc.). */
export interface AudioSetting {
  sample_rate?: number;
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
  voice_id: string;
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

function buildTTSBody(
  params: TTSParams,
  stream: boolean,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: params.model,
    text: params.text,
    stream,
    output_format: params.outputFormat ?? "hex",
  };
  if (params.voiceSetting !== undefined)
    body.voice_setting = params.voiceSetting;
  if (params.audioSetting !== undefined)
    body.audio_setting = params.audioSetting;
  if (params.languageBoost !== undefined)
    body.language_boost = params.languageBoost;
  if (params.voiceModify !== undefined)
    body.voice_modify = params.voiceModify;
  if (params.pronunciationDict !== undefined)
    body.pronunciation_dict = params.pronunciationDict;
  if (params.timbreWeights !== undefined)
    body.timbre_weights = params.timbreWeights;
  if (params.subtitleEnable) body.subtitle_enable = true;
  return body;
}

function buildAsyncBody(
  params: AsyncCreateParams,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: params.model ?? "speech-2.8-hd",
    voice_setting: params.voiceSetting,
  };
  if (params.text !== undefined) body.text = params.text;
  if (params.textFileId !== undefined) body.text_file_id = params.textFileId;
  if (params.audioSetting !== undefined)
    body.audio_setting = params.audioSetting;
  if (params.languageBoost !== undefined)
    body.language_boost = params.languageBoost;
  if (params.voiceModify !== undefined)
    body.voice_modify = params.voiceModify;
  if (params.pronunciationDict !== undefined)
    body.pronunciation_dict = params.pronunciationDict;
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
   *   voiceSetting: { voice_id: "male-qn-qingse" },
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

  // ── WebSocket TTS (placeholder) ──────────────────────────────────────

  // TODO: WebSocket-based real-time TTS via `wss://{host}/ws/v1/t2a_v2`.
  //
  // The connect() method will open a WebSocket connection and return a
  // SpeechConnection object that supports:
  //   - send(text) -> Promise<AudioResponse>  (collect all chunks)
  //   - sendStream(text) -> AsyncGenerator<Buffer>  (yield chunks)
  //   - close() -> Promise<void>
  //
  // Protocol: task_start -> task_started -> task_continue -> task_continued* -> task_finish -> task_finished
  //
  // This will be implemented separately due to WebSocket complexity.

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
  async asyncCreate(
    params: AsyncCreateParams,
  ): Promise<Record<string, unknown>> {
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
    const interval =
      params.pollInterval ?? this._client.pollInterval;
    const timeout =
      params.pollTimeout ?? this._client.pollTimeout;

    const pollResult = await pollTask(
      this._client._httpClient,
      T2A_ASYNC_QUERY_PATH,
      taskId,
      { pollInterval: interval, pollTimeout: timeout },
    );

    // Step 3: Retrieve file info for the download URL
    const fileId = String(pollResult.file_id ?? "");
    const fileInfo: FileInfo = await this._client.files.retrieve(fileId);
    const downloadUrl = fileInfo.download_url ?? "";

    return {
      taskId,
      status: String(pollResult.status ?? "Success"),
      fileId,
      downloadUrl,
    };
  }
}
