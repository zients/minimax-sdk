/**
 * Voice resource -- clone, design, list, and delete voices.
 *
 * Provides the {@link Voice} class for MiniMax's voice management APIs.
 */

import { APIResource } from "../resource.js";
import {
  AudioResponse,
  buildAudioResponse,
  decodeHexAudio,
} from "../audio.js";
import type { FileInfo } from "./files.js";

// ── Types ───────────────────────────────────────────────────────────────────

export interface ClonePrompt {
  promptAudio: string;
  promptText: string;
}

export interface VoiceCloneResult {
  voiceId: string;
  demoAudio?: string | null;
  inputSensitive?: unknown;
}

export interface VoiceDesignResult {
  voiceId: string;
  trialAudio?: AudioResponse | null;
}

export interface VoiceInfo {
  voiceId: string;
  voiceName?: string;
  description: string[];
  createdTime?: string;
}

export interface VoiceList {
  systemVoice: VoiceInfo[];
  voiceCloning: VoiceInfo[];
  voiceGeneration: VoiceInfo[];
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function buildCloneBody(opts: {
  file_id: string;
  voice_id: string;
  clone_prompt?: ClonePrompt;
  text?: string;
  model?: string;
  language_boost?: string;
  need_noise_reduction: boolean;
  need_volume_normalization: boolean;
}): Record<string, unknown> {
  const numericFileId = Number(opts.file_id);
  if (!Number.isFinite(numericFileId)) {
    throw new Error("file_id must be a numeric string");
  }
  const body: Record<string, unknown> = {
    file_id: numericFileId,
    voice_id: opts.voice_id,
    need_noise_reduction: opts.need_noise_reduction,
    need_volume_normalization: opts.need_volume_normalization,
  };
  if (opts.clone_prompt !== undefined) {
    body.clone_prompt = {
      prompt_audio: opts.clone_prompt.promptAudio,
      prompt_text: opts.clone_prompt.promptText,
    };
  }
  if (opts.text !== undefined) body.text = opts.text;
  if (opts.model !== undefined) body.model = opts.model;
  if (opts.language_boost !== undefined) body.language_boost = opts.language_boost;
  return body;
}

function parseCloneResult(
  resp: Record<string, unknown>,
  voiceId: string,
): VoiceCloneResult {
  const demoAudioUrl = resp.demo_audio as string | undefined;

  return {
    voiceId,
    demoAudio: demoAudioUrl || null,
    inputSensitive: resp.input_sensitive ?? null,
  };
}

function parseDesignResult(
  resp: Record<string, unknown>,
): VoiceDesignResult {
  const rawTrial = resp.trial_audio;
  let trialAudio: AudioResponse | null = null;

  if (rawTrial) {
    if (typeof rawTrial === "string") {
      // API returns trial_audio as a hex-encoded string (no metadata)
      const audioBytes = decodeHexAudio(rawTrial);
      trialAudio = new AudioResponse({
        data: audioBytes,
        size: audioBytes.length,
      });
    } else {
      // Nested dict structure (fallback)
      trialAudio = buildAudioResponse(rawTrial as Record<string, unknown>);
    }
  }

  return {
    voiceId: String(resp.voice_id),
    trialAudio: trialAudio,
  };
}

function parseVoiceList(resp: Record<string, unknown>): VoiceList {
  const systemVoice = (resp.system_voice ?? []) as Record<string, unknown>[];
  const voiceCloning = (resp.voice_cloning ?? []) as Record<string, unknown>[];
  const voiceGeneration = (resp.voice_generation ?? []) as Record<string, unknown>[];

  return {
    systemVoice: systemVoice.map(parseVoiceInfo),
    voiceCloning: voiceCloning.map(parseVoiceInfo),
    voiceGeneration: voiceGeneration.map(parseVoiceInfo),
  };
}

function parseVoiceInfo(v: Record<string, unknown>): VoiceInfo {
  return {
    voiceId: String(v.voice_id ?? ""),
    voiceName: v.voice_name != null ? String(v.voice_name) : undefined,
    description: (v.description as string[]) ?? [],
    createdTime: v.created_time != null ? String(v.created_time) : undefined,
  };
}

// ── Voice resource ──────────────────────────────────────────────────────────

/**
 * Voice resource for cloning, designing, listing, and deleting voices.
 */
export class Voice extends APIResource {
  /**
   * Upload an audio file for voice cloning or as a prompt audio reference.
   *
   * This is a convenience method that delegates to
   * {@link Files.upload | client.files.upload()}.
   *
   * @param file - A filesystem path (string) or a Buffer/Blob of file data.
   * @param purpose - The intended use of the file. Must be "voice_clone"
   *   (default) or "prompt_audio".
   * @returns A {@link FileInfo} describing the uploaded file.
   */
  async uploadAudio(
    file: string | Buffer | Blob,
    purpose: string = "voice_clone",
  ): Promise<FileInfo> {
    return this._client.files.upload(file, purpose);
  }

  /**
   * Clone a voice from a previously uploaded audio file.
   *
   * @param fileId - The identifier of the uploaded audio file to clone from.
   * @param voiceId - The desired voice identifier for the cloned voice.
   * @param opts.clonePrompt - Optional prompt audio reference with
   *   "promptAudio" (file ID) and "promptText" keys.
   * @param opts.text - Optional text to generate a demo audio clip with the
   *   cloned voice. Requires model to be set as well.
   * @param opts.model - TTS model to use for generating the demo audio
   *   (e.g. "speech-2.8-hd"). Required when text is provided.
   * @param opts.languageBoost - Optional language code to boost recognition
   *   accuracy (e.g. "en", "zh").
   * @param opts.needNoiseReduction - Whether to apply noise reduction to the
   *   source audio before cloning.
   * @param opts.needVolumeNormalization - Whether to normalize volume of the
   *   source audio before cloning.
   * @returns A {@link VoiceCloneResult} containing the voiceId and,
   *   when text/model are provided, a demoAudio URL.
   */
  async clone(
    fileId: string,
    voiceId: string,
    opts: {
      clonePrompt?: ClonePrompt;
      text?: string;
      model?: string;
      languageBoost?: string;
      needNoiseReduction?: boolean;
      needVolumeNormalization?: boolean;
    } = {},
  ): Promise<VoiceCloneResult> {
    const body = buildCloneBody({
      file_id: fileId,
      voice_id: voiceId,
      clone_prompt: opts.clonePrompt,
      text: opts.text,
      model: opts.model,
      language_boost: opts.languageBoost,
      need_noise_reduction: opts.needNoiseReduction ?? false,
      need_volume_normalization: opts.needVolumeNormalization ?? false,
    });
    const resp = await this._client.request("POST", "/v1/voice_clone", {
      json: body,
    });
    return parseCloneResult(resp, voiceId);
  }

  /**
   * Design a new voice from a natural-language description.
   *
   * @param prompt - A description of the desired voice characteristics
   *   (e.g. "warm female narrator with a British accent").
   * @param previewText - Text to synthesise as a trial audio clip so you
   *   can hear the designed voice.
   * @param opts.voiceId - Optional identifier to assign to the designed voice.
   *   If not provided, the API generates one.
   * @returns A {@link VoiceDesignResult} containing the voiceId and a
   *   trialAudio {@link AudioResponse}.
   */
  async design(
    prompt: string,
    previewText: string,
    opts: {
      voiceId?: string;
    } = {},
  ): Promise<VoiceDesignResult> {
    const body: Record<string, unknown> = {
      prompt,
      preview_text: previewText,
    };
    if (opts.voiceId !== undefined) body.voice_id = opts.voiceId;

    const resp = await this._client.request("POST", "/v1/voice_design", {
      json: body,
    });
    return parseDesignResult(resp);
  }

  /**
   * List available voices.
   *
   * @param voiceType - Filter by type. One of "system", "voice_cloning",
   *   "voice_generation", or "all" (default).
   * @returns A {@link VoiceList} with separate lists for system, cloned,
   *   and generated voices (populated according to voiceType).
   */
  async list(voiceType: string = "all"): Promise<VoiceList> {
    const resp = await this._client.request("POST", "/v1/get_voice", {
      json: { voice_type: voiceType },
    });
    return parseVoiceList(resp);
  }

  /**
   * Delete a voice.
   *
   * @param voiceId - The identifier of the voice to delete.
   * @param voiceType - The type of voice being deleted -- "voice_cloning"
   *   or "voice_generation".
   */
  async delete(voiceId: string, voiceType: string): Promise<void> {
    await this._client.request("POST", "/v1/delete_voice", {
      json: { voice_id: voiceId, voice_type: voiceType },
    });
  }
}
