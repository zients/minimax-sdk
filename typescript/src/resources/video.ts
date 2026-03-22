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
  promptOptimizer?: boolean;
  fastPretreatment?: boolean;
  duration?: number;
  resolution?: string;
  callbackUrl?: string;
  firstFrameImage?: string;
  lastFrameImage?: string;
  subjectReference?: SubjectReference[];
}

export interface VideoResult {
  taskId: string;
  status: string;
  fileId: string;
  downloadUrl?: string;
  videoWidth: number;
  videoHeight: number;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

const CREATE_PATH = "/v1/video_generation";
const QUERY_PATH = "/v1/query/video_generation";

function buildRequestBody(params: VideoCreateParams): Record<string, unknown> {
  const body: Record<string, unknown> = { model: params.model };
  if (params.prompt !== undefined) body.prompt = params.prompt;
  if (params.promptOptimizer !== undefined)
    body.prompt_optimizer = params.promptOptimizer;
  if (params.fastPretreatment !== undefined)
    body.fast_pretreatment = params.fastPretreatment;
  if (params.duration !== undefined) body.duration = params.duration;
  if (params.resolution !== undefined) body.resolution = params.resolution;
  if (params.callbackUrl !== undefined) body.callback_url = params.callbackUrl;
  if (params.firstFrameImage !== undefined)
    body.first_frame_image = params.firstFrameImage;
  if (params.lastFrameImage !== undefined)
    body.last_frame_image = params.lastFrameImage;
  if (params.subjectReference !== undefined)
    body.subject_reference = params.subjectReference;
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
      json: buildRequestBody(params),
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
    params: VideoCreateParams,
    opts: {
      pollInterval?: number;
      pollTimeout?: number;
    } = {},
  ): Promise<VideoResult> {
    // 1. Create the generation task.
    const createResp = await this.create(params);
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
      taskId: taskId,
      status: String(pollResp.status ?? "Success"),
      fileId: fileId,
      downloadUrl: fileInfo.downloadUrl,
      videoWidth: Number(pollResp.video_width ?? 0),
      videoHeight: Number(pollResp.video_height ?? 0),
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
    return this._generate(
      {
        model,
        prompt,
        promptOptimizer: opts.promptOptimizer ?? true,
        fastPretreatment: opts.fastPretreatment ?? false,
        duration: opts.duration ?? 6,
        resolution: opts.resolution,
        callbackUrl: opts.callbackUrl,
      },
      {
        pollInterval: opts.pollInterval,
        pollTimeout: opts.pollTimeout,
      },
    );
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
    return this._generate(
      {
        model,
        prompt: opts.prompt,
        promptOptimizer: opts.promptOptimizer ?? true,
        fastPretreatment: opts.fastPretreatment ?? false,
        duration: opts.duration ?? 6,
        resolution: opts.resolution,
        callbackUrl: opts.callbackUrl,
        firstFrameImage: firstFrameImage,
      },
      {
        pollInterval: opts.pollInterval,
        pollTimeout: opts.pollTimeout,
      },
    );
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
    return this._generate(
      {
        model: opts.model ?? "MiniMax-Hailuo-02",
        prompt: opts.prompt,
        promptOptimizer: opts.promptOptimizer ?? true,
        fastPretreatment: opts.fastPretreatment ?? false,
        duration: opts.duration ?? 6,
        resolution: opts.resolution,
        callbackUrl: opts.callbackUrl,
        firstFrameImage: opts.firstFrameImage,
        lastFrameImage: lastFrameImage,
      },
      {
        pollInterval: opts.pollInterval,
        pollTimeout: opts.pollTimeout,
      },
    );
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
    return this._generate(
      {
        model: opts.model ?? "S2V-01",
        prompt: opts.prompt,
        promptOptimizer: opts.promptOptimizer ?? true,
        callbackUrl: opts.callbackUrl,
        subjectReference: subjectReference,
      },
      {
        pollInterval: opts.pollInterval,
        pollTimeout: opts.pollTimeout,
      },
    );
  }
}
