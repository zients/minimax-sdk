/**
 * Audio utilities for the MiniMax SDK.
 *
 * Provides AudioResponse class and hex decoding helpers,
 * matching the Python SDK's _audio.py.
 */

import { writeFile } from "node:fs/promises";

// ── Hex decoding ────────────────────────────────────────────────────────────

export function decodeHexAudio(hex: string): Buffer {
  return Buffer.from(hex, "hex");
}

// ── AudioResponse ───────────────────────────────────────────────────────────

export interface AudioResponseData {
  data: Buffer;
  duration?: number;
  sampleRate?: number;
  format?: string;
  size?: number;
}

export class AudioResponse {
  readonly data: Buffer;
  readonly duration: number;
  readonly sampleRate: number;
  readonly format: string;
  readonly size: number;

  constructor(opts: AudioResponseData) {
    this.data = opts.data;
    this.duration = opts.duration ?? 0;
    this.sampleRate = opts.sampleRate ?? 0;
    this.format = opts.format ?? "mp3";
    this.size = opts.size ?? opts.data.length;
  }

  async save(path: string): Promise<void> {
    await writeFile(path, this.data);
  }

  toBase64(): string {
    return this.data.toString("base64");
  }
}

// ── Response builders ───────────────────────────────────────────────────────

export function buildAudioResponse(
  resp: Record<string, unknown>,
): AudioResponse {
  const data = (resp.data ?? {}) as Record<string, unknown>;
  const extraInfo = (resp.extra_info ??
    data.extra_info ??
    {}) as Record<string, unknown>;

  const hexStr =
    (data.audio as string) ??
    (resp.audio_hex as string) ??
    (resp.audio as string) ??
    "";
  const audioBytes = decodeHexAudio(hexStr);

  return new AudioResponse({
    data: audioBytes,
    duration: Number(
      extraInfo.audio_length ?? resp.audio_length ?? resp.duration ?? 0,
    ),
    sampleRate: Number(
      extraInfo.audio_sample_rate ??
        resp.audio_sample_rate ??
        resp.sample_rate ??
        0,
    ),
    format: String(
      extraInfo.audio_format ?? resp.audio_format ?? resp.format ?? "mp3",
    ),
    size: Number(extraInfo.audio_size ?? resp.audio_size ?? audioBytes.length),
  });
}
