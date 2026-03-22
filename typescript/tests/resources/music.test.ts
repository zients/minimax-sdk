import { describe, it, expect, vi, beforeEach } from "vitest";
import { Music } from "../../src/resources/music.js";
import { AudioResponse } from "../../src/audio.js";

// ── Mock client factory ─────────────────────────────────────────────────────

function createMockClient() {
  return {
    request: vi.fn(),
    requestAnthropic: vi.fn(),
    streamRequest: vi.fn(),
    streamRequestAnthropic: vi.fn(),
    requestBytes: vi.fn(),
    upload: vi.fn(),
    pollInterval: 5,
    pollTimeout: 600,
    files: {
      retrieve: vi.fn(),
    },
  } as any;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function makeMusicResponse(audioHex: string = "") {
  return {
    data: { audio: audioHex },
    extra_info: {
      music_duration: 30,
      music_sample_rate: 44100,
      audio_format: "mp3",
      music_size: 1024,
    },
  };
}

function makeMusicUrlResponse(url: string) {
  return {
    data: { audio: url },
    extra_info: {
      music_duration: 30,
      music_sample_rate: 44100,
      audio_format: "mp3",
      music_size: 0,
    },
  };
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Music", () => {
  let mockClient: ReturnType<typeof createMockClient>;
  let music: Music;

  beforeEach(() => {
    mockClient = createMockClient();
    music = new Music(mockClient);
  });

  // ── generate() ──────────────────────────────────────────────────────

  describe("generate()", () => {
    it("calls request with correct method, path, and body for minimal params", async () => {
      mockClient.request.mockResolvedValue(makeMusicUrlResponse("https://cdn.minimax.io/music.mp3"));

      const result = await music.generate();

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/music_generation",
        {
          json: {
            model: "music-2.5+",
            stream: false,
            output_format: "url",
            lyrics_optimizer: false,
            is_instrumental: false,
          },
        },
      );

      expect(result).toBeInstanceOf(AudioResponse);
    });

    it("uses a custom model", async () => {
      mockClient.request.mockResolvedValue(makeMusicUrlResponse("https://cdn.minimax.io/m.mp3"));

      await music.generate("music-3.0");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.model).toBe("music-3.0");
    });

    it("passes prompt option", async () => {
      mockClient.request.mockResolvedValue(makeMusicUrlResponse("https://example.com/m.mp3"));

      await music.generate("music-2.5+", {
        prompt: "Upbeat pop song with electric guitar",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.prompt).toBe("Upbeat pop song with electric guitar");
    });

    it("passes lyrics option", async () => {
      mockClient.request.mockResolvedValue(makeMusicUrlResponse("https://example.com/m.mp3"));

      await music.generate("music-2.5+", {
        lyrics: "[Verse]\nHello world\n[Chorus]\nLa la la",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.lyrics).toBe("[Verse]\nHello world\n[Chorus]\nLa la la");
    });

    it("passes outputFormat as output_format", async () => {
      const hexAudio = Buffer.from("music data").toString("hex");
      mockClient.request.mockResolvedValue(makeMusicResponse(hexAudio));

      await music.generate("music-2.5+", {
        outputFormat: "hex",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.output_format).toBe("hex");
    });

    it("passes lyricsOptimizer and isInstrumental", async () => {
      mockClient.request.mockResolvedValue(makeMusicUrlResponse("https://example.com/m.mp3"));

      await music.generate("music-2.5+", {
        lyricsOptimizer: true,
        isInstrumental: true,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.lyrics_optimizer).toBe(true);
      expect(body.is_instrumental).toBe(true);
    });

    it("passes audioSetting option", async () => {
      mockClient.request.mockResolvedValue(makeMusicUrlResponse("https://example.com/m.mp3"));

      await music.generate("music-2.5+", {
        audioSetting: { sampleRate: 48000, bitrate: 320, format: "wav" },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.audio_setting).toEqual({ sample_rate: 48000, bitrate: 320, format: "wav" });
    });

    it("returns AudioResponse with hex-decoded data", async () => {
      const hexAudio = Buffer.from("raw audio bytes").toString("hex");
      mockClient.request.mockResolvedValue(makeMusicResponse(hexAudio));

      const result = await music.generate("music-2.5+", { outputFormat: "hex" });

      expect(result).toBeInstanceOf(AudioResponse);
      expect(result.data).toEqual(Buffer.from("raw audio bytes"));
      expect(result.duration).toBe(30);
      expect(result.sampleRate).toBe(44100);
      expect(result.format).toBe("mp3");
      expect(result.size).toBe(1024);
    });

    it("returns AudioResponse with URL-encoded data", async () => {
      const url = "https://cdn.minimax.io/music/file123.mp3";
      mockClient.request.mockResolvedValue(makeMusicUrlResponse(url));

      const result = await music.generate("music-2.5+", { outputFormat: "url" });

      expect(result).toBeInstanceOf(AudioResponse);
      // URL mode stores the URL string as UTF-8 bytes
      expect(result.data.toString("utf-8")).toBe(url);
    });

    it("passes all options together", async () => {
      mockClient.request.mockResolvedValue(makeMusicUrlResponse("https://example.com/m.mp3"));

      await music.generate("music-2.5+", {
        prompt: "Chill lo-fi beats",
        lyrics: "[Verse]\nRelaxing vibes",
        outputFormat: "url",
        lyricsOptimizer: true,
        isInstrumental: false,
        audioSetting: { sampleRate: 44100, format: "mp3" },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.model).toBe("music-2.5+");
      expect(body.prompt).toBe("Chill lo-fi beats");
      expect(body.lyrics).toBe("[Verse]\nRelaxing vibes");
      expect(body.output_format).toBe("url");
      expect(body.lyrics_optimizer).toBe(true);
      expect(body.is_instrumental).toBe(false);
      expect(body.audio_setting).toEqual({ sample_rate: 44100, format: "mp3" });
      expect(body.stream).toBe(false);
    });
  });

  // ── generateStream() ────────────────────────────────────────────────

  describe("generateStream()", () => {
    it("calls streamRequest with stream=true and yields audio chunks", async () => {
      const chunk1Hex = Buffer.from("musicchunk1").toString("hex");
      const chunk2Hex = Buffer.from("musicchunk2").toString("hex");

      const sseLines: string[] = [
        `data: ${JSON.stringify({ type: "data", data: { audio: chunk1Hex } })}`,
        "",
        `data: ${JSON.stringify({ type: "data", data: { audio: chunk2Hex } })}`,
        "",
      ];

      const stream = new ReadableStream<string>({
        start(controller) {
          for (const line of sseLines) {
            controller.enqueue(line);
          }
          controller.close();
        },
      });

      mockClient.streamRequest.mockResolvedValue(stream);

      const chunks: Buffer[] = [];
      for await (const chunk of music.generateStream()) {
        chunks.push(chunk);
      }

      expect(mockClient.streamRequest).toHaveBeenCalledOnce();
      const callArgs = mockClient.streamRequest.mock.calls[0]!;
      expect(callArgs[0]).toBe("POST");
      expect(callArgs[1]).toBe("/v1/music_generation");
      expect(callArgs[2].json.stream).toBe(true);
      // Streaming always uses hex output_format
      expect(callArgs[2].json.output_format).toBe("hex");

      expect(chunks).toHaveLength(2);
      expect(chunks[0]).toEqual(Buffer.from("musicchunk1"));
      expect(chunks[1]).toEqual(Buffer.from("musicchunk2"));
    });

    it("passes optional params for streaming", async () => {
      const stream = new ReadableStream<string>({
        start(controller) {
          controller.close();
        },
      });
      mockClient.streamRequest.mockResolvedValue(stream);

      const chunks: Buffer[] = [];
      for await (const chunk of music.generateStream("music-3.0", {
        prompt: "Jazz",
        lyrics: "[Verse]\nBa ba ba",
        lyricsOptimizer: true,
        isInstrumental: false,
        audioSetting: { sampleRate: 48000 },
      })) {
        chunks.push(chunk);
      }

      const body = mockClient.streamRequest.mock.calls[0]![2].json;
      expect(body.model).toBe("music-3.0");
      expect(body.prompt).toBe("Jazz");
      expect(body.lyrics).toBe("[Verse]\nBa ba ba");
      expect(body.lyrics_optimizer).toBe(true);
      expect(body.is_instrumental).toBe(false);
      expect(body.audio_setting).toEqual({ sample_rate: 48000 });
    });
  });

  // ── generateLyrics() ────────────────────────────────────────────────

  describe("generateLyrics()", () => {
    it("calls request for write_full_song mode", async () => {
      mockClient.request.mockResolvedValue({
        data: {
          song_title: "Summer Breeze",
          style_tags: "pop, upbeat, summer",
          lyrics: "[Verse]\nSummer breeze blowing...\n[Chorus]\nOh summer!",
        },
      });

      const result = await music.generateLyrics("write_full_song", {
        prompt: "A happy summer song",
      });

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/lyrics_generation",
        {
          json: {
            mode: "write_full_song",
            prompt: "A happy summer song",
          },
        },
      );

      expect(result.songTitle).toBe("Summer Breeze");
      expect(result.styleTags).toBe("pop, upbeat, summer");
      expect(result.lyrics).toContain("[Verse]");
    });

    it("calls request for edit mode with existing lyrics", async () => {
      mockClient.request.mockResolvedValue({
        data: {
          song_title: "Night Sky",
          style_tags: "ballad, slow",
          lyrics: "[Verse]\nStars are shining bright...",
        },
      });

      const result = await music.generateLyrics("edit", {
        lyrics: "[Verse]\nStars are bright...",
        title: "Night Sky",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.mode).toBe("edit");
      expect(body.lyrics).toBe("[Verse]\nStars are bright...");
      expect(body.title).toBe("Night Sky");
      expect(result.songTitle).toBe("Night Sky");
    });

    it("omits optional fields when not provided", async () => {
      mockClient.request.mockResolvedValue({
        data: {
          song_title: "Untitled",
          style_tags: "",
          lyrics: "",
        },
      });

      await music.generateLyrics("write_full_song");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body).toEqual({ mode: "write_full_song" });
      expect(body).not.toHaveProperty("prompt");
      expect(body).not.toHaveProperty("lyrics");
      expect(body).not.toHaveProperty("title");
    });

    it("handles response without data wrapper (fallback)", async () => {
      // parseLyricsResult falls back to resp itself when data is absent
      mockClient.request.mockResolvedValue({
        song_title: "Direct Song",
        style_tags: "rock",
        lyrics: "[Verse]\nRock on",
      });

      const result = await music.generateLyrics("write_full_song", {
        prompt: "Rock song",
      });

      expect(result.songTitle).toBe("Direct Song");
      expect(result.styleTags).toBe("rock");
      expect(result.lyrics).toBe("[Verse]\nRock on");
    });
  });
});
