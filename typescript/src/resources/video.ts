/**
 * Video resource -- text-to-video, image-to-video, frames-to-video,
 * and subject-to-video generation.
 *
 * High-level methods compose: create() -> poll loop -> files.retrieve()
 * to return a fully-resolved {@link VideoResult} with a download URL.
 */

import { APIResource } from "../resource.js";
import { pollTask } from "../polling.js";

// ── Types ───────────────────────────────────────────────────────────────────

export interface SubjectReference {
  type: string;
  image: string;
}

export interface VideoCreateParams {
  model: string;
  prompt?: string;
  prompt_optimizer?: boolean;
  fast_pretreatment?: boolean;
  duration?: number;
  resolution?: string;
  callback_url?: string;
  first_frame_image?: string;
  last_frame_image?: string;
  subject_reference?: SubjectReference[];
}

export interface VideoResult {
  task_id: string;
  status: string;
  file_id: string;
  download_url?: string;
  video_width: number;
  video_height: number;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

const CREATE_PATH = "/v1/video_generation";
const QUERY_PATH = "/v1/query/video_generation";

function buildRequestBody(opts: {
  model: string;
  prompt?: string;
  prompt_optimizer?: boolean;
  fast_pretreatment?: boolean;
  duration?: number;
  resolution?: string;
  callback_url?: string;
  first_frame_image?: string;
  last_frame_image?: string;
  subject_reference?: SubjectReference[];
}): Record<string, unknown> {
  const body: Record<string, unknown> = { model: opts.model };
  if (opts.prompt !== undefined) body.prompt = opts.prompt;
  if (opts.prompt_optimizer !== undefined)
    body.prompt_optimizer = opts.prompt_optimizer;
  if (opts.fast_pretreatment !== undefined)
    body.fast_pretreatment = opts.fast_pretreatment;
  if (opts.duration !== undefined) body.duration = opts.duration;
  if (opts.resolution !== undefined) body.resolution = opts.resolution;
  if (opts.callback_url !== undefined) body.callback_url = opts.callback_url;
  if (opts.first_frame_image !== undefined)
    body.first_frame_image = opts.first_frame_image;
  if (opts.last_frame_image !== undefined)
    body.last_frame_image = opts.last_frame_image;
  if (opts.subject_reference !== undefined)
    body.subject_reference = opts.subject_reference;
  return body;
}

// ── Video resource ──────────────────────────────────────────────────────────

/**
 * Video generation resource.
 *
 * High-level methods ({@link Video.textToVideo}, {@link Video.imageToVideo},
 * {@link Video.framesToVideo}, {@link Video.subjectToVideo}) automatically
 * poll until the generation task completes and return a {@link VideoResult}
 * with a temporary download URL.
 *
 * Low-level methods ({@link Video.create}, {@link Video.query}) give direct
 * access to the underlying API endpoints.
 */
export class Video extends APIResource {
  // ── Low-level ──────────────────────────────────────────────────────

  /**
   * Create a video generation task.
   *
   * Sends a POST to /v1/video_generation with the supplied parameters
   * as the JSON body.
   *
   * @returns The raw API response containing `task_id`.
   */
  async create(
    params: VideoCreateParams,
  ): Promise<Record<string, unknown>> {
    return this._client.request("POST", CREATE_PATH, {
      json: params as unknown as Record<string, unknown>,
    });
  }

  /**
   * Query the status of a video generation task.
   *
   * Sends a GET to /v1/query/video_generation.
   *
   * @param taskId - The task identifier returned by {@link create}.
   * @returns The raw API response containing `status`, and on success
   *   `file_id`, `video_width`, `video_height`.
   */
  async query(taskId: string): Promise<Record<string, unknown>> {
    return this._client.request("GET", QUERY_PATH, {
      params: { task_id: taskId },
    });
  }

  // ── Private helper ─────────────────────────────────────────────────

  private async _generate(
    body: Record<string, unknown>,
    opts: {
      pollInterval?: number;
      pollTimeout?: number;
    } = {},
  ): Promise<VideoResult> {
    // 1. Create the generation task.
    const createResp = await this.create(
      body as unknown as VideoCreateParams,
    );
    const taskId = String(createResp.task_id);

    // 2. Poll until the task reaches a terminal state.
    const interval =
      opts.pollInterval ?? this._client.pollInterval;
    const timeout =
      opts.pollTimeout ?? this._client.pollTimeout;

    const pollResp = await pollTask(
      this._client._httpClient,
      QUERY_PATH,
      taskId,
      { pollInterval: interval, pollTimeout: timeout },
    );

    // 3. Retrieve the file to obtain a download URL.
    const fileId = String(pollResp.file_id ?? "");
    const fileInfo = await this._client.files.retrieve(fileId);

    return {
      task_id: taskId,
      status: String(pollResp.status ?? "Success"),
      file_id: fileId,
      download_url: fileInfo.download_url,
      video_width: Number(pollResp.video_width ?? 0),
      video_height: Number(pollResp.video_height ?? 0),
    };
  }

  // ── High-level ─────────────────────────────────────────────────────

  /**
   * Generate a video from a text prompt (T2V).
   *
   * Creates a generation task, polls until completion, and resolves
   * the file download URL.
   *
   * @param prompt - Text description of the desired video content.
   * @param model - Model identifier. Defaults to "MiniMax-Hailuo-2.3".
   * @param opts.promptOptimizer - Whether to optimize the prompt server-side.
   * @param opts.fastPretreatment - Enable fast pre-treatment mode.
   * @param opts.duration - Video duration in seconds (default 6).
   * @param opts.resolution - Output resolution (e.g. "1280x720").
   * @param opts.callbackUrl - Optional webhook URL for completion notification.
   * @param opts.pollInterval - Override client-level polling interval (seconds).
   * @param opts.pollTimeout - Override client-level polling timeout (seconds).
   * @returns A {@link VideoResult} with task metadata and a temporary
   *   download URL (valid for ~1 hour).
   */
  async textToVideo(
    prompt: string,
    model: string = "MiniMax-Hailuo-2.3",
    opts: {
      promptOptimizer?: boolean;
      fastPretreatment?: boolean;
      duration?: number;
      resolution?: string;
      callbackUrl?: string;
      pollInterval?: number;
      pollTimeout?: number;
    } = {},
  ): Promise<VideoResult> {
    const body = buildRequestBody({
      model,
      prompt,
      prompt_optimizer: opts.promptOptimizer ?? true,
      fast_pretreatment: opts.fastPretreatment ?? false,
      duration: opts.duration ?? 6,
      resolution: opts.resolution,
      callback_url: opts.callbackUrl,
    });
    return this._generate(body, {
      pollInterval: opts.pollInterval,
      pollTimeout: opts.pollTimeout,
    });
  }

  /**
   * Generate a video from a first-frame image (I2V).
   *
   * Creates a generation task, polls until completion, and resolves
   * the file download URL.
   *
   * @param firstFrameImage - URL or base64 data URI of the first frame.
   * @param model - Model identifier. Defaults to "MiniMax-Hailuo-2.3".
   * @param opts.prompt - Optional text prompt to guide generation.
   * @param opts.promptOptimizer - Whether to optimize the prompt server-side.
   * @param opts.fastPretreatment - Enable fast pre-treatment mode.
   * @param opts.duration - Video duration in seconds (default 6).
   * @param opts.resolution - Output resolution (e.g. "1280x720").
   * @param opts.callbackUrl - Optional webhook URL for completion notification.
   * @param opts.pollInterval - Override client-level polling interval (seconds).
   * @param opts.pollTimeout - Override client-level polling timeout (seconds).
   * @returns A {@link VideoResult} with task metadata and a temporary
   *   download URL (valid for ~1 hour).
   */
  async imageToVideo(
    firstFrameImage: string,
    model: string = "MiniMax-Hailuo-2.3",
    opts: {
      prompt?: string;
      promptOptimizer?: boolean;
      fastPretreatment?: boolean;
      duration?: number;
      resolution?: string;
      callbackUrl?: string;
      pollInterval?: number;
      pollTimeout?: number;
    } = {},
  ): Promise<VideoResult> {
    const body = buildRequestBody({
      model,
      prompt: opts.prompt,
      prompt_optimizer: opts.promptOptimizer ?? true,
      fast_pretreatment: opts.fastPretreatment ?? false,
      duration: opts.duration ?? 6,
      resolution: opts.resolution,
      callback_url: opts.callbackUrl,
      first_frame_image: firstFrameImage,
    });
    return this._generate(body, {
      pollInterval: opts.pollInterval,
      pollTimeout: opts.pollTimeout,
    });
  }

  /**
   * Generate a video from frame endpoints (FL2V).
   *
   * Interpolates between an optional first frame and a required last
   * frame to produce a video.
   *
   * @param lastFrameImage - URL or base64 data URI of the last frame (required).
   * @param opts.firstFrameImage - URL or base64 data URI of the first frame.
   * @param opts.model - Model identifier. Defaults to "MiniMax-Hailuo-02".
   * @param opts.prompt - Optional text prompt to guide generation.
   * @param opts.promptOptimizer - Whether to optimize the prompt server-side.
   * @param opts.fastPretreatment - Enable fast pre-treatment mode.
   * @param opts.duration - Video duration in seconds (default 6).
   * @param opts.resolution - Output resolution (e.g. "1280x720").
   * @param opts.callbackUrl - Optional webhook URL for completion notification.
   * @param opts.pollInterval - Override client-level polling interval (seconds).
   * @param opts.pollTimeout - Override client-level polling timeout (seconds).
   * @returns A {@link VideoResult} with task metadata and a temporary
   *   download URL (valid for ~1 hour).
   */
  async framesToVideo(
    lastFrameImage: string,
    opts: {
      firstFrameImage?: string;
      model?: string;
      prompt?: string;
      promptOptimizer?: boolean;
      fastPretreatment?: boolean;
      duration?: number;
      resolution?: string;
      callbackUrl?: string;
      pollInterval?: number;
      pollTimeout?: number;
    } = {},
  ): Promise<VideoResult> {
    const body = buildRequestBody({
      model: opts.model ?? "MiniMax-Hailuo-02",
      prompt: opts.prompt,
      prompt_optimizer: opts.promptOptimizer ?? true,
      fast_pretreatment: opts.fastPretreatment ?? false,
      duration: opts.duration ?? 6,
      resolution: opts.resolution,
      callback_url: opts.callbackUrl,
      first_frame_image: opts.firstFrameImage,
      last_frame_image: lastFrameImage,
    });
    return this._generate(body, {
      pollInterval: opts.pollInterval,
      pollTimeout: opts.pollTimeout,
    });
  }

  /**
   * Generate a video driven by subject references (S2V).
   *
   * Uses one or more subject reference images to drive video generation.
   *
   * @param subjectReference - List of subject reference objects, each
   *   containing "type" and "image" keys.
   * @param opts.prompt - Optional text prompt to guide generation.
   * @param opts.model - Model identifier. Defaults to "S2V-01".
   * @param opts.promptOptimizer - Whether to optimize the prompt server-side.
   * @param opts.callbackUrl - Optional webhook URL for completion notification.
   * @param opts.pollInterval - Override client-level polling interval (seconds).
   * @param opts.pollTimeout - Override client-level polling timeout (seconds).
   * @returns A {@link VideoResult} with task metadata and a temporary
   *   download URL (valid for ~1 hour).
   */
  async subjectToVideo(
    subjectReference: SubjectReference[],
    opts: {
      prompt?: string;
      model?: string;
      promptOptimizer?: boolean;
      callbackUrl?: string;
      pollInterval?: number;
      pollTimeout?: number;
    } = {},
  ): Promise<VideoResult> {
    const body = buildRequestBody({
      model: opts.model ?? "S2V-01",
      prompt: opts.prompt,
      prompt_optimizer: opts.promptOptimizer ?? true,
      callback_url: opts.callbackUrl,
      subject_reference: subjectReference,
    });
    return this._generate(body, {
      pollInterval: opts.pollInterval,
      pollTimeout: opts.pollTimeout,
    });
  }
}
