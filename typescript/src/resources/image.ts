/**
 * Image resource -- image generation via MiniMax's Image Generation API.
 *
 * Provides the {@link Image} class for text-to-image (T2I) and
 * image-to-image (I2I) generation via `POST /v1/image_generation`.
 */

import { APIResource } from "../resource.js";

// ── Types ───────────────────────────────────────────────────────────────────

export interface ImageSubjectReference {
  type: string;
  image_file: string;
}

export interface ImageGenerateParams {
  prompt: string;
  model?: string;
  aspect_ratio?: string;
  width?: number;
  height?: number;
  response_format?: string;
  seed?: number;
  n?: number;
  prompt_optimizer?: boolean;
  subject_reference?: ImageSubjectReference[];
}

export interface ImageResult {
  id: string;
  image_urls?: string[];
  image_base64?: string[];
  success_count: number;
  failed_count: number;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function buildImageBody(params: {
  prompt: string;
  model: string;
  aspect_ratio?: string;
  width?: number;
  height?: number;
  response_format: string;
  seed?: number;
  n: number;
  prompt_optimizer: boolean;
  subject_reference?: ImageSubjectReference[];
}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: params.model,
    prompt: params.prompt,
    response_format: params.response_format,
    n: params.n,
    prompt_optimizer: params.prompt_optimizer,
  };

  if (params.aspect_ratio !== undefined) body.aspect_ratio = params.aspect_ratio;
  if (params.width !== undefined) body.width = params.width;
  if (params.height !== undefined) body.height = params.height;
  if (params.seed !== undefined) body.seed = params.seed;
  if (params.subject_reference !== undefined)
    body.subject_reference = params.subject_reference;

  return body;
}

function parseImageResult(resp: Record<string, unknown>): ImageResult {
  const data = (resp.data ?? {}) as Record<string, unknown>;
  const metadata = (resp.metadata ?? {}) as Record<string, unknown>;

  return {
    id: String(resp.id),
    image_urls: (data.image_urls as string[] | undefined) ?? undefined,
    image_base64: (data.image_base64 as string[] | undefined) ?? undefined,
    success_count: Number(metadata.success_count ?? 0),
    failed_count: Number(metadata.failed_count ?? 0),
  };
}

// ── Image resource ──────────────────────────────────────────────────────────

/**
 * Image generation resource.
 *
 * Supports text-to-image (T2I) and image-to-image (I2I) generation via
 * the same {@link Image.generate} method. Pass `subjectReference` for
 * I2I mode.
 */
export class Image extends APIResource {
  /**
   * Generate one or more images from a text prompt.
   *
   * @param prompt - The text description of the desired image(s).
   * @param model - The model identifier (default "image-01").
   * @param opts.aspectRatio - Aspect ratio hint (e.g. "16:9"). Mutually
   *   exclusive with explicit width/height.
   * @param opts.width - Desired image width in pixels.
   * @param opts.height - Desired image height in pixels.
   * @param opts.responseFormat - "url" (default) returns temporary download
   *   URLs; "base64" returns base64-encoded image data.
   * @param opts.seed - Random seed for reproducibility.
   * @param opts.n - Number of images to generate (default 1).
   * @param opts.promptOptimizer - Whether to let the API optimise the prompt.
   * @param opts.subjectReference - A list of subject-reference objects for
   *   I2I mode. Each should contain "type" (e.g. "character") and
   *   "image_file" (a public URL or base64 data URL).
   * @returns An {@link ImageResult} containing generated image URLs or
   *   base64 data, plus success/failure counts.
   */
  async generate(
    prompt: string,
    model: string = "image-01",
    opts: {
      aspectRatio?: string;
      width?: number;
      height?: number;
      responseFormat?: string;
      seed?: number;
      n?: number;
      promptOptimizer?: boolean;
      subjectReference?: ImageSubjectReference[];
    } = {},
  ): Promise<ImageResult> {
    const body = buildImageBody({
      prompt,
      model,
      aspect_ratio: opts.aspectRatio,
      width: opts.width,
      height: opts.height,
      response_format: opts.responseFormat ?? "url",
      seed: opts.seed,
      n: opts.n ?? 1,
      prompt_optimizer: opts.promptOptimizer ?? false,
      subject_reference: opts.subjectReference,
    });

    const resp = await this._client.request("POST", "/v1/image_generation", {
      json: body,
    });
    return parseImageResult(resp);
  }
}
