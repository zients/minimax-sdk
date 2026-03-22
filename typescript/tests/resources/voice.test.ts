import { describe, it, expect, vi, beforeEach } from "vitest";
import { Voice } from "../../src/resources/voice.js";
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
      upload: vi.fn(),
    },
  } as any;
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Voice", () => {
  let mockClient: ReturnType<typeof createMockClient>;
  let voice: Voice;

  beforeEach(() => {
    mockClient = createMockClient();
    voice = new Voice(mockClient);
  });

  // ── uploadAudio() ───────────────────────────────────────────────────

  describe("uploadAudio()", () => {
    it("delegates to client.files.upload with default purpose", async () => {
      const fileInfo = {
        fileId: "f_001",
        bytes: 1000,
        createdAt: 1700000000,
        filename: "audio.wav",
        purpose: "voice_clone",
      };
      mockClient.files.upload.mockResolvedValue(fileInfo);

      const result = await voice.uploadAudio(Buffer.from("audio data"));

      expect(mockClient.files.upload).toHaveBeenCalledOnce();
      expect(mockClient.files.upload).toHaveBeenCalledWith(
        Buffer.from("audio data"),
        "voice_clone",
      );
      expect(result).toEqual(fileInfo);
    });

    it("allows custom purpose", async () => {
      mockClient.files.upload.mockResolvedValue({ fileId: "f_002" });

      await voice.uploadAudio(Buffer.from("data"), "prompt_audio");

      expect(mockClient.files.upload).toHaveBeenCalledWith(Buffer.from("data"), "prompt_audio");
    });
  });

  // ── clone() ─────────────────────────────────────────────────────────

  describe("clone()", () => {
    it("calls request with correct path and body for minimal params", async () => {
      mockClient.request.mockResolvedValue({
        demo_audio: null,
        input_sensitive: null,
      });

      const result = await voice.clone("12345", "my-voice-id");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith("POST", "/v1/voice_clone", {
        json: {
          file_id: 12345,
          voice_id: "my-voice-id",
          need_noise_reduction: false,
          need_volume_normalization: false,
        },
      });

      expect(result.voiceId).toBe("my-voice-id");
      expect(result.demoAudio).toBeNull();
    });

    it("includes clonePrompt in the body", async () => {
      mockClient.request.mockResolvedValue({});

      await voice.clone("100", "v-clone", {
        clonePrompt: { promptAudio: "audio_file_id", promptText: "Hello world" },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.clone_prompt).toEqual({
        prompt_audio: "audio_file_id",
        prompt_text: "Hello world",
      });
    });

    it("includes text and model for demo generation", async () => {
      mockClient.request.mockResolvedValue({
        demo_audio: "https://cdn.minimax.io/demo.mp3",
      });

      const result = await voice.clone("100", "v-clone", {
        text: "This is a demo.",
        model: "speech-2.8-hd",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.text).toBe("This is a demo.");
      expect(body.model).toBe("speech-2.8-hd");
      expect(result.demoAudio).toBe("https://cdn.minimax.io/demo.mp3");
    });

    it("includes languageBoost option", async () => {
      mockClient.request.mockResolvedValue({});

      await voice.clone("100", "v-clone", {
        languageBoost: "en",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.language_boost).toBe("en");
    });

    it("includes noise reduction and volume normalization", async () => {
      mockClient.request.mockResolvedValue({});

      await voice.clone("100", "v-clone", {
        needNoiseReduction: true,
        needVolumeNormalization: true,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.need_noise_reduction).toBe(true);
      expect(body.need_volume_normalization).toBe(true);
    });

    it("converts file_id to number", async () => {
      mockClient.request.mockResolvedValue({});

      await voice.clone("99999", "v-clone");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.file_id).toBe(99999);
      expect(typeof body.file_id).toBe("number");
    });

    it("throws on non-numeric file_id", async () => {
      await expect(voice.clone("abc", "v-clone")).rejects.toThrow(
        "file_id must be a numeric string",
      );
      expect(mockClient.request).not.toHaveBeenCalled();
    });

    it("returns input_sensitive from response", async () => {
      mockClient.request.mockResolvedValue({
        input_sensitive: "flagged_content",
      });

      const result = await voice.clone("100", "v-clone");
      expect(result.inputSensitive).toBe("flagged_content");
    });
  });

  // ── design() ────────────────────────────────────────────────────────

  describe("design()", () => {
    it("calls request with correct path and body", async () => {
      mockClient.request.mockResolvedValue({
        voice_id: "designed-v1",
        trial_audio: null,
      });

      const result = await voice.design(
        "warm female narrator with a British accent",
        "Hello, welcome to the show.",
      );

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith("POST", "/v1/voice_design", {
        json: {
          prompt: "warm female narrator with a British accent",
          preview_text: "Hello, welcome to the show.",
        },
      });

      expect(result.voiceId).toBe("designed-v1");
      expect(result.trialAudio).toBeNull();
    });

    it("includes voiceId when provided", async () => {
      mockClient.request.mockResolvedValue({
        voice_id: "custom-voice-id",
        trial_audio: null,
      });

      await voice.design("A deep male voice", "Test audio", {
        voiceId: "custom-voice-id",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.voice_id).toBe("custom-voice-id");
    });

    it("decodes hex trial_audio as AudioResponse", async () => {
      const hexAudio = Buffer.from("trial audio bytes").toString("hex");
      mockClient.request.mockResolvedValue({
        voice_id: "designed-v2",
        trial_audio: hexAudio,
      });

      const result = await voice.design("A bright voice", "Preview text");

      expect(result.trialAudio).toBeInstanceOf(AudioResponse);
      expect(result.trialAudio!.data).toEqual(Buffer.from("trial audio bytes"));
    });

    it("handles nested dict trial_audio structure", async () => {
      const hexAudio = Buffer.from("nested audio").toString("hex");
      mockClient.request.mockResolvedValue({
        voice_id: "designed-v3",
        trial_audio: {
          data: { audio: hexAudio },
          extra_info: {
            audio_length: 2.0,
            audio_sample_rate: 22050,
          },
        },
      });

      const result = await voice.design("A calm voice", "Preview");

      expect(result.trialAudio).toBeInstanceOf(AudioResponse);
      expect(result.trialAudio!.data).toEqual(Buffer.from("nested audio"));
    });

    it("returns null trial_audio when not present", async () => {
      mockClient.request.mockResolvedValue({
        voice_id: "designed-v4",
      });

      const result = await voice.design("A voice", "Text");
      expect(result.trialAudio).toBeNull();
    });
  });

  // ── list() ──────────────────────────────────────────────────────────

  describe("list()", () => {
    it("calls request with default voiceType 'all'", async () => {
      mockClient.request.mockResolvedValue({
        system_voice: [{ voice_id: "sv-001", description: ["System voice 1"] }],
        voice_cloning: [
          { voice_id: "vc-001", voice_name: "My Clone", description: ["Cloned voice"] },
        ],
        voice_generation: [],
      });

      const result = await voice.list();

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith("POST", "/v1/get_voice", {
        json: { voice_type: "all" },
      });

      expect(result.systemVoice).toHaveLength(1);
      expect(result.systemVoice[0]!.voiceId).toBe("sv-001");
      expect(result.voiceCloning).toHaveLength(1);
      expect(result.voiceCloning[0]!.voiceName).toBe("My Clone");
      expect(result.voiceGeneration).toHaveLength(0);
    });

    it("filters by voiceType", async () => {
      mockClient.request.mockResolvedValue({
        system_voice: [],
        voice_cloning: [{ voice_id: "vc-001", description: ["A cloned voice"] }],
        voice_generation: [],
      });

      await voice.list("voice_cloning");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.voice_type).toBe("voice_cloning");
    });

    it("parses VoiceInfo fields correctly", async () => {
      mockClient.request.mockResolvedValue({
        system_voice: [
          {
            voice_id: "sv-001",
            voice_name: "System Voice",
            description: ["A system voice", "General purpose"],
            created_time: "2024-01-01T00:00:00Z",
          },
        ],
        voice_cloning: [],
        voice_generation: [],
      });

      const result = await voice.list();

      const v = result.systemVoice[0]!;
      expect(v.voiceId).toBe("sv-001");
      expect(v.voiceName).toBe("System Voice");
      expect(v.description).toEqual(["A system voice", "General purpose"]);
      expect(v.createdTime).toBe("2024-01-01T00:00:00Z");
    });

    it("handles empty lists gracefully", async () => {
      mockClient.request.mockResolvedValue({});

      const result = await voice.list();

      expect(result.systemVoice).toEqual([]);
      expect(result.voiceCloning).toEqual([]);
      expect(result.voiceGeneration).toEqual([]);
    });
  });

  // ── delete() ────────────────────────────────────────────────────────

  describe("delete()", () => {
    it("calls request with correct path and body", async () => {
      mockClient.request.mockResolvedValue({});

      await voice.delete("vc-001", "voice_cloning");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith("POST", "/v1/delete_voice", {
        json: { voice_id: "vc-001", voice_type: "voice_cloning" },
      });
    });

    it("can delete a voice_generation type", async () => {
      mockClient.request.mockResolvedValue({});

      await voice.delete("vg-001", "voice_generation");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.voice_id).toBe("vg-001");
      expect(body.voice_type).toBe("voice_generation");
    });
  });
});
