import { describe, it, expect, vi, beforeEach } from "vitest";
import { Speech } from "../../src/resources/speech.js";
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
    _httpClient: {
      request: vi.fn(),
    },
    files: {
      retrieve: vi.fn(),
      upload: vi.fn(),
    },
  } as any;
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Speech", () => {
  let mockClient: ReturnType<typeof createMockClient>;
  let speech: Speech;

  beforeEach(() => {
    mockClient = createMockClient();
    speech = new Speech(mockClient);
  });

  // ── tts() ───────────────────────────────────────────────────────────────

  describe("tts()", () => {
    it("calls request with correct method, path, and body", async () => {
      // buildAudioResponse expects data.audio as hex
      const hexAudio = Buffer.from("hello audio").toString("hex");
      mockClient.request.mockResolvedValue({
        data: { audio: hexAudio },
        extra_info: {
          audio_length: 1.5,
          audio_sample_rate: 32000,
          audio_format: "mp3",
          audio_size: 1024,
        },
      });

      const result = await speech.tts({
        text: "Hello world",
        model: "speech-2.8-hd",
        voiceSetting: { voice_id: "male-qn-qingse" },
      });

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/t2a_v2",
        {
          json: {
            model: "speech-2.8-hd",
            text: "Hello world",
            stream: false,
            output_format: "hex",
            voice_setting: { voice_id: "male-qn-qingse" },
          },
        },
      );

      expect(result).toBeInstanceOf(AudioResponse);
      expect(result.data).toEqual(Buffer.from("hello audio"));
    });

    it("includes optional params in the body", async () => {
      const hexAudio = Buffer.from("audio").toString("hex");
      mockClient.request.mockResolvedValue({
        data: { audio: hexAudio },
      });

      await speech.tts({
        text: "Test",
        model: "speech-2.8-hd",
        voiceSetting: { voice_id: "female-tianmei" },
        audioSetting: { sample_rate: 24000, format: "wav" },
        languageBoost: "en",
        voiceModify: { pitch: 1.1 },
        pronunciationDict: { hello: "HH EH L OW" },
        timbreWeights: [{ voice_id: "v1", weight: 0.5 }],
        subtitleEnable: true,
        outputFormat: "hex",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.voice_setting).toEqual({ voice_id: "female-tianmei" });
      expect(body.audio_setting).toEqual({ sample_rate: 24000, format: "wav" });
      expect(body.language_boost).toBe("en");
      expect(body.voice_modify).toEqual({ pitch: 1.1 });
      expect(body.pronunciation_dict).toEqual({ hello: "HH EH L OW" });
      expect(body.timbre_weights).toEqual([{ voice_id: "v1", weight: 0.5 }]);
      expect(body.subtitle_enable).toBe(true);
    });

    it("defaults output_format to hex", async () => {
      mockClient.request.mockResolvedValue({
        data: { audio: "" },
      });

      await speech.tts({
        text: "Test",
        model: "speech-2.8-hd",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.output_format).toBe("hex");
    });

    it("returns an AudioResponse with metadata", async () => {
      const hexAudio = Buffer.from("audio data").toString("hex");
      mockClient.request.mockResolvedValue({
        data: { audio: hexAudio },
        extra_info: {
          audio_length: 2.0,
          audio_sample_rate: 44100,
          audio_format: "wav",
          audio_size: 2048,
        },
      });

      const result = await speech.tts({
        text: "Hello",
        model: "speech-2.8-hd",
      });

      expect(result.duration).toBe(2.0);
      expect(result.sampleRate).toBe(44100);
      expect(result.format).toBe("wav");
      expect(result.size).toBe(2048);
    });
  });

  // ── ttsStream() ─────────────────────────────────────────────────────────

  describe("ttsStream()", () => {
    it("calls streamRequest with stream=true and yields audio chunks", async () => {
      const chunk1Hex = Buffer.from("chunk1").toString("hex");
      const chunk2Hex = Buffer.from("chunk2").toString("hex");

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
      for await (const chunk of speech.ttsStream({
        text: "Hello world",
        model: "speech-2.8-hd",
        voiceSetting: { voice_id: "male-qn-qingse" },
      })) {
        chunks.push(chunk);
      }

      expect(mockClient.streamRequest).toHaveBeenCalledOnce();
      const callArgs = mockClient.streamRequest.mock.calls[0]!;
      expect(callArgs[0]).toBe("POST");
      expect(callArgs[1]).toBe("/v1/t2a_v2");
      expect(callArgs[2].json.stream).toBe(true);

      expect(chunks).toHaveLength(2);
      expect(chunks[0]).toEqual(Buffer.from("chunk1"));
      expect(chunks[1]).toEqual(Buffer.from("chunk2"));
    });
  });

  // ── asyncCreate() ──────────────────────────────────────────────────────

  describe("asyncCreate()", () => {
    it("calls request with correct path and body for text input", async () => {
      const response = { task_id: "task_001", file_id: "file_001", task_token: "token_abc" };
      mockClient.request.mockResolvedValue(response);

      const result = await speech.asyncCreate({
        text: "A very long text to synthesize.",
        voiceSetting: { voice_id: "male-qn-qingse" },
      });

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/t2a_async_v2",
        {
          json: {
            model: "speech-2.8-hd",
            text: "A very long text to synthesize.",
            voice_setting: { voice_id: "male-qn-qingse" },
          },
        },
      );
      expect(result).toEqual(response);
    });

    it("supports textFileId as input instead of text", async () => {
      mockClient.request.mockResolvedValue({ task_id: "task_002" });

      await speech.asyncCreate({
        textFileId: 12345,
        voiceSetting: { voice_id: "male-qn-qingse" },
        model: "speech-2.8-hd",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.text_file_id).toBe(12345);
      expect(body).not.toHaveProperty("text");
    });

    it("includes optional params", async () => {
      mockClient.request.mockResolvedValue({ task_id: "task_003" });

      await speech.asyncCreate({
        text: "Long text.",
        model: "speech-2.8-hd",
        voiceSetting: { voice_id: "v1" },
        audioSetting: { sample_rate: 24000 },
        languageBoost: "zh",
        voiceModify: { intensity: 0.8 },
        pronunciationDict: { test: "T EH S T" },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.audio_setting).toEqual({ sample_rate: 24000 });
      expect(body.language_boost).toBe("zh");
      expect(body.voice_modify).toEqual({ intensity: 0.8 });
      expect(body.pronunciation_dict).toEqual({ test: "T EH S T" });
    });
  });

  // ── asyncQuery() ──────────────────────────────────────────────────────

  describe("asyncQuery()", () => {
    it("calls request with GET and query params", async () => {
      const response = { task_id: "task_001", status: "Processing" };
      mockClient.request.mockResolvedValue(response);

      const result = await speech.asyncQuery("task_001");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "GET",
        "/v1/query/t2a_async_query_v2",
        {
          params: { task_id: "task_001" },
        },
      );
      expect(result).toEqual(response);
    });
  });

  // ── asyncGenerate() ───────────────────────────────────────────────────

  describe("asyncGenerate()", () => {
    it("composes create + poll + retrieve into a TaskResult", async () => {
      // Step 1: asyncCreate returns task_id
      mockClient.request.mockResolvedValueOnce({
        task_id: "task_100",
        file_id: "file_100",
        task_token: "token_xyz",
      });

      // Step 2: pollTask calls _httpClient.request (poll query)
      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "task_100",
        status: "Success",
        file_id: "file_200",
      });

      // Step 3: files.retrieve returns file info with download URL
      mockClient.files.retrieve.mockResolvedValueOnce({
        file_id: "file_200",
        bytes: 50000,
        created_at: 1700000000,
        filename: "output.mp3",
        purpose: "t2a_async",
        download_url: "https://cdn.minimax.io/files/file_200",
      });

      const result = await speech.asyncGenerate({
        text: "Long text to synthesize.",
        voiceSetting: { voice_id: "male-qn-qingse" },
        pollInterval: 1,
        pollTimeout: 10,
      });

      expect(result.taskId).toBe("task_100");
      expect(result.status).toBe("Success");
      expect(result.fileId).toBe("file_200");
      expect(result.downloadUrl).toBe("https://cdn.minimax.io/files/file_200");

      // Verify asyncCreate was called
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/t2a_async_v2",
        expect.any(Object),
      );

      // Verify files.retrieve was called with the file_id from poll
      expect(mockClient.files.retrieve).toHaveBeenCalledWith("file_200");
    });

    it("uses client defaults for pollInterval and pollTimeout", async () => {
      mockClient.request.mockResolvedValueOnce({ task_id: "task_200" });

      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "task_200",
        status: "Success",
        file_id: "file_300",
      });

      mockClient.files.retrieve.mockResolvedValueOnce({
        file_id: "file_300",
        bytes: 1000,
        created_at: 1700000000,
        filename: "out.mp3",
        purpose: "t2a_async",
        download_url: "https://cdn.minimax.io/files/file_300",
      });

      await speech.asyncGenerate({
        text: "Test",
        voiceSetting: { voice_id: "v1" },
      });

      // The pollTask was called; it would use client.pollInterval (5) and
      // client.pollTimeout (600) as defaults. Just verify no error was thrown
      // and the result was returned.
      expect(mockClient.files.retrieve).toHaveBeenCalledWith("file_300");
    });
  });
});
