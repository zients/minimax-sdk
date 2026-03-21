import { describe, it, expect, vi } from "vitest";
import {
  decodeHexAudio,
  AudioResponse,
  buildAudioResponse,
} from "../src/audio.js";

// ── decodeHexAudio ──────────────────────────────────────────────────────────

describe("decodeHexAudio", () => {
  it("should decode hex string to Buffer", () => {
    const buf = decodeHexAudio("48656c6c6f");
    expect(buf).toBeInstanceOf(Buffer);
    expect(buf.toString("utf8")).toBe("Hello");
  });

  it("should return empty Buffer for empty string", () => {
    const buf = decodeHexAudio("");
    expect(buf.length).toBe(0);
  });

  it("should handle lowercase hex", () => {
    const buf = decodeHexAudio("ff00ab");
    expect(buf[0]).toBe(0xff);
    expect(buf[1]).toBe(0x00);
    expect(buf[2]).toBe(0xab);
  });

  it("should handle uppercase hex", () => {
    const buf = decodeHexAudio("FF00AB");
    expect(buf[0]).toBe(0xff);
    expect(buf[1]).toBe(0x00);
    expect(buf[2]).toBe(0xab);
  });
});

// ── AudioResponse ───────────────────────────────────────────────────────────

describe("AudioResponse", () => {
  it("should set all properties from constructor options", () => {
    const data = Buffer.from("audio-data");
    const audio = new AudioResponse({
      data,
      duration: 3.5,
      sampleRate: 44100,
      format: "wav",
      size: 1024,
    });

    expect(audio.data).toBe(data);
    expect(audio.duration).toBe(3.5);
    expect(audio.sampleRate).toBe(44100);
    expect(audio.format).toBe("wav");
    expect(audio.size).toBe(1024);
  });

  it("should default duration to 0", () => {
    const audio = new AudioResponse({ data: Buffer.from("x") });
    expect(audio.duration).toBe(0);
  });

  it("should default sampleRate to 0", () => {
    const audio = new AudioResponse({ data: Buffer.from("x") });
    expect(audio.sampleRate).toBe(0);
  });

  it("should default format to 'mp3'", () => {
    const audio = new AudioResponse({ data: Buffer.from("x") });
    expect(audio.format).toBe("mp3");
  });

  it("should default size to data.length", () => {
    const data = Buffer.from("12345");
    const audio = new AudioResponse({ data });
    expect(audio.size).toBe(5);
  });

  describe("toBase64()", () => {
    it("should return base64 encoded data", () => {
      const data = Buffer.from("Hello, World!");
      const audio = new AudioResponse({ data });
      expect(audio.toBase64()).toBe(data.toString("base64"));
    });

    it("should return empty string for empty data", () => {
      const audio = new AudioResponse({ data: Buffer.from("") });
      expect(audio.toBase64()).toBe("");
    });
  });

  describe("save()", () => {
    it("should call writeFile with the correct path and data", async () => {
      const { writeFile } = await import("node:fs/promises");
      vi.mock("node:fs/promises", () => ({
        writeFile: vi.fn().mockResolvedValue(undefined),
      }));

      const data = Buffer.from("audio-bytes");
      const audio = new AudioResponse({ data });
      await audio.save("/tmp/test-output.mp3");

      const mockedWriteFile = writeFile as unknown as ReturnType<typeof vi.fn>;
      expect(mockedWriteFile).toHaveBeenCalledWith(
        "/tmp/test-output.mp3",
        data,
      );
    });
  });
});

// ── buildAudioResponse ──────────────────────────────────────────────────────

describe("buildAudioResponse", () => {
  it("should extract audio from data.audio field", () => {
    // "48656c6c6f" = "Hello"
    const resp = {
      data: {
        audio: "48656c6c6f",
      },
    };
    const audio = buildAudioResponse(resp);
    expect(audio.data.toString("utf8")).toBe("Hello");
  });

  it("should extract audio from audio_hex field", () => {
    const resp = {
      audio_hex: "48656c6c6f",
    };
    const audio = buildAudioResponse(resp);
    expect(audio.data.toString("utf8")).toBe("Hello");
  });

  it("should extract audio from top-level audio field", () => {
    const resp = {
      audio: "48656c6c6f",
    };
    const audio = buildAudioResponse(resp);
    expect(audio.data.toString("utf8")).toBe("Hello");
  });

  it("should extract duration from extra_info.audio_length", () => {
    const resp = {
      data: {
        audio: "ff",
        extra_info: { audio_length: 5.2 },
      },
    };
    const audio = buildAudioResponse(resp);
    expect(audio.duration).toBe(5.2);
  });

  it("should extract duration from top-level audio_length", () => {
    const resp = {
      audio: "ff",
      audio_length: 3.0,
    };
    const audio = buildAudioResponse(resp);
    expect(audio.duration).toBe(3.0);
  });

  it("should extract duration from top-level duration", () => {
    const resp = {
      audio: "ff",
      duration: 7.1,
    };
    const audio = buildAudioResponse(resp);
    expect(audio.duration).toBe(7.1);
  });

  it("should extract sampleRate from extra_info.audio_sample_rate", () => {
    const resp = {
      data: {
        audio: "ff",
        extra_info: { audio_sample_rate: 44100 },
      },
    };
    const audio = buildAudioResponse(resp);
    expect(audio.sampleRate).toBe(44100);
  });

  it("should extract sampleRate from top-level audio_sample_rate", () => {
    const resp = {
      audio: "ff",
      audio_sample_rate: 22050,
    };
    const audio = buildAudioResponse(resp);
    expect(audio.sampleRate).toBe(22050);
  });

  it("should extract sampleRate from top-level sample_rate", () => {
    const resp = {
      audio: "ff",
      sample_rate: 16000,
    };
    const audio = buildAudioResponse(resp);
    expect(audio.sampleRate).toBe(16000);
  });

  it("should extract format from extra_info.audio_format", () => {
    const resp = {
      data: {
        audio: "ff",
        extra_info: { audio_format: "wav" },
      },
    };
    const audio = buildAudioResponse(resp);
    expect(audio.format).toBe("wav");
  });

  it("should extract format from top-level audio_format", () => {
    const resp = {
      audio: "ff",
      audio_format: "ogg",
    };
    const audio = buildAudioResponse(resp);
    expect(audio.format).toBe("ogg");
  });

  it("should default format to 'mp3'", () => {
    const resp = { audio: "ff" };
    const audio = buildAudioResponse(resp);
    expect(audio.format).toBe("mp3");
  });

  it("should extract size from extra_info.audio_size", () => {
    const resp = {
      data: {
        audio: "ff",
        extra_info: { audio_size: 2048 },
      },
    };
    const audio = buildAudioResponse(resp);
    expect(audio.size).toBe(2048);
  });

  it("should extract size from top-level audio_size", () => {
    const resp = {
      audio: "ff",
      audio_size: 512,
    };
    const audio = buildAudioResponse(resp);
    expect(audio.size).toBe(512);
  });

  it("should default size to decoded buffer length", () => {
    // "aabbcc" = 3 bytes
    const resp = { audio: "aabbcc" };
    const audio = buildAudioResponse(resp);
    expect(audio.size).toBe(3);
  });

  it("should prefer extra_info from top-level resp over data.extra_info", () => {
    const resp = {
      extra_info: { audio_length: 10 },
      data: {
        audio: "ff",
        extra_info: { audio_length: 5 },
      },
    };
    const audio = buildAudioResponse(resp);
    expect(audio.duration).toBe(10);
  });

  it("should handle empty response gracefully", () => {
    const resp = {};
    const audio = buildAudioResponse(resp);
    expect(audio.data.length).toBe(0);
    expect(audio.duration).toBe(0);
    expect(audio.sampleRate).toBe(0);
    expect(audio.format).toBe("mp3");
  });
});
