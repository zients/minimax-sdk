/**
 * Music resource -- music generation and lyrics generation.
 *
 * Provides the {@link Music} class for the MiniMax Music Generation API
 * (`POST /v1/music_generation`) and Lyrics Generation API
 * (`POST /v1/lyrics_generation`).
 */

import { APIResource } from "../resource.js";
import {
  AudioResponse,
  decodeHexAudio,
} from "../audio.js";
import { parseNativeSSEAudioChunks } from "../streaming.js";

// ── Types ───────────────────────────────────────────────────────────────────

export interface MusicAudioSetting {
  sampleRate?: number;
  bitrate?: number;
  format?: string;
}

export interface MusicGenerateParams {
  model?: string;
  prompt?: string;
  lyrics?: string;
  outputFormat?: string;
  lyricsOptimizer?: boolean;
  isInstrumental?: boolean;
  audioSetting?: MusicAudioSetting;
}

export interface MusicGenerateStreamParams {
  model?: string;
  prompt?: string;
  lyrics?: string;
  lyricsOptimizer?: boolean;
  isInstrumental?: boolean;
  audioSetting?: MusicAudioSetting;
}

export interface LyricsGenerateParams {
  mode: string;
  prompt?: string;
  lyrics?: string;
  title?: string;
}

export interface LyricsResult {
  songTitle: string;
  styleTags: string;
  lyrics: string;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function buildMusicBody(opts: {
  model: string;
  prompt?: string;
  lyrics?: string;
  stream: boolean;
  outputFormat?: string;
  lyricsOptimizer: boolean;
  isInstrumental: boolean;
  audioSetting?: MusicAudioSetting;
}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: opts.model,
    stream: opts.stream,
    lyrics_optimizer: opts.lyricsOptimizer,
    is_instrumental: opts.isInstrumental,
  };

  if (opts.prompt !== undefined) body.prompt = opts.prompt;
  if (opts.lyrics !== undefined) body.lyrics = opts.lyrics;
  if (opts.outputFormat !== undefined) body.output_format = opts.outputFormat;
  if (opts.audioSetting) {
    body.audio_setting = {
      sample_rate: opts.audioSetting.sampleRate,
      bitrate: opts.audioSetting.bitrate,
      format: opts.audioSetting.format,
    };
  }

  return body;
}

function buildAudioResponseFromMusic(
  resp: Record<string, unknown>,
): AudioResponse {
  const dataSection = (resp.data ?? {}) as Record<string, unknown>;
  const extraInfo = (resp.extra_info ?? {}) as Record<string, unknown>;

  const audioRaw = String(dataSection.audio ?? "");

  let audioBytes: Buffer;
  if (audioRaw && !audioRaw.startsWith("http://") && !audioRaw.startsWith("https://")) {
    audioBytes = decodeHexAudio(audioRaw);
  } else if (audioRaw) {
    // URL mode -- store the URL string encoded as bytes
    audioBytes = Buffer.from(audioRaw, "utf-8");
  } else {
    audioBytes = Buffer.alloc(0);
  }

  const duration = Number(extraInfo.music_duration ?? 0);
  const sampleRate = Number(extraInfo.music_sample_rate ?? 0);
  const audioFormat = String(extraInfo.audio_format ?? "mp3");
  const size = Number(extraInfo.music_size ?? 0) || audioBytes.length;

  return new AudioResponse({
    data: audioBytes,
    duration,
    sampleRate,
    format: audioFormat,
    size,
  });
}

function buildLyricsBody(opts: {
  mode: string;
  prompt?: string;
  lyrics?: string;
  title?: string;
}): Record<string, unknown> {
  const body: Record<string, unknown> = { mode: opts.mode };

  if (opts.prompt !== undefined) body.prompt = opts.prompt;
  if (opts.lyrics !== undefined) body.lyrics = opts.lyrics;
  if (opts.title !== undefined) body.title = opts.title;

  return body;
}

function parseLyricsResult(resp: Record<string, unknown>): LyricsResult {
  const data = (resp.data ?? resp) as Record<string, unknown>;

  return {
    songTitle: String(data.song_title ?? ""),
    styleTags: String(data.style_tags ?? ""),
    lyrics: String(data.lyrics ?? ""),
  };
}

// ── Music resource ──────────────────────────────────────────────────────────

/**
 * Music and lyrics generation resource.
 */
export class Music extends APIResource {
  /**
   * Generate music from a text prompt and/or lyrics.
   *
   * @param model - The model identifier (default "music-2.5+").
   * @param opts.prompt - A text description of the desired music style/mood.
   * @param opts.lyrics - Lyrics for the generated track.
   * @param opts.outputFormat - "url" (default) returns a download URL;
   *   "hex" returns hex-encoded audio data.
   * @param opts.lyricsOptimizer - Whether to let the API optimise the lyrics.
   * @param opts.isInstrumental - Generate an instrumental track (no vocals).
   * @param opts.audioSetting - Optional dict with keys like "sample_rate",
   *   "bitrate", "format".
   * @returns An {@link AudioResponse} containing the generated audio data.
   */
  async generate(
    model: string = "music-2.5+",
    opts: {
      prompt?: string;
      lyrics?: string;
      outputFormat?: string;
      lyricsOptimizer?: boolean;
      isInstrumental?: boolean;
      audioSetting?: MusicAudioSetting;
    } = {},
  ): Promise<AudioResponse> {
    const body = buildMusicBody({
      model,
      prompt: opts.prompt,
      lyrics: opts.lyrics,
      stream: false,
      outputFormat: opts.outputFormat ?? "hex",
      lyricsOptimizer: opts.lyricsOptimizer ?? false,
      isInstrumental: opts.isInstrumental ?? false,
      audioSetting: opts.audioSetting,
    });

    const resp = await this._client.request("POST", "/v1/music_generation", {
      json: body,
    });
    return buildAudioResponseFromMusic(resp);
  }

  /**
   * Generate music as a stream of decoded audio chunks.
   *
   * Streaming always uses output_format="hex" (API requirement). Each
   * yielded chunk is a Buffer of decoded audio bytes from one SSE event.
   *
   * @param model - The model identifier (default "music-2.5+").
   * @param opts.prompt - A text description of the desired music style/mood.
   * @param opts.lyrics - Lyrics for the generated track.
   * @param opts.lyricsOptimizer - Whether to let the API optimise the lyrics.
   * @param opts.isInstrumental - Generate an instrumental track (no vocals).
   * @param opts.audioSetting - Optional dict with keys like "sample_rate",
   *   "bitrate", "format".
   * @returns An async generator yielding Buffer chunks of audio data.
   */
  async *generateStream(
    model: string = "music-2.5+",
    opts: {
      prompt?: string;
      lyrics?: string;
      lyricsOptimizer?: boolean;
      isInstrumental?: boolean;
      audioSetting?: MusicAudioSetting;
    } = {},
  ): AsyncGenerator<Buffer> {
    const body = buildMusicBody({
      model,
      prompt: opts.prompt,
      lyrics: opts.lyrics,
      stream: true,
      outputFormat: "hex",
      lyricsOptimizer: opts.lyricsOptimizer ?? false,
      isInstrumental: opts.isInstrumental ?? false,
      audioSetting: opts.audioSetting,
    });

    const stream = await this._client.streamRequest(
      "POST",
      "/v1/music_generation",
      { json: body },
    );

    for await (const chunk of parseNativeSSEAudioChunks(stream)) {
      yield chunk;
    }
  }

  /**
   * Generate or edit lyrics.
   *
   * @param mode - Generation mode -- "write_full_song" to create new
   *   lyrics from a prompt, or "edit" to refine existing lyrics.
   * @param opts.prompt - A text description of the desired song theme/style.
   * @param opts.lyrics - Existing lyrics (required for "edit" mode).
   * @param opts.title - Desired song title hint.
   * @returns A {@link LyricsResult} containing the song title, style tags,
   *   and generated lyrics.
   */
  async generateLyrics(
    mode: string,
    opts: {
      prompt?: string;
      lyrics?: string;
      title?: string;
    } = {},
  ): Promise<LyricsResult> {
    const body = buildLyricsBody({
      mode,
      prompt: opts.prompt,
      lyrics: opts.lyrics,
      title: opts.title,
    });

    const resp = await this._client.request("POST", "/v1/lyrics_generation", {
      json: body,
    });
    return parseLyricsResult(resp);
  }
}
