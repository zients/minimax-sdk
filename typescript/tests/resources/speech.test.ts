import { describe, it, expect, vi, beforeEach } from "vitest";
import { EventEmitter } from "events";
import { Speech, SpeechConnection } from "../../src/resources/speech.js";
import { AudioResponse } from "../../src/audio.js";
import { MiniMaxError } from "../../src/error.js";

// ── Mock WebSocket ──────────────────────────────────────────────────────────

class MockWebSocket extends EventEmitter {
  send = vi.fn();
  close = vi.fn();

  // Override `off` so it returns `this` like real ws does,
  // while also actually removing the listener.
  off(event: string, handler: (...args: any[]) => void): this {
    this.removeListener(event, handler);
    return this;
  }
}

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
      baseURL: "https://api.minimax.chat",
      getApiKey: () => "test-api-key-123",
    },
    files: {
      retrieve: vi.fn(),
      upload: vi.fn(),
    },
  } as any;
}

// ── Helper: create a SpeechConnection with a mock WebSocket ─────────────────

function createConnection(
  ws?: MockWebSocket,
  config?: Record<string, unknown>,
): { conn: SpeechConnection; ws: MockWebSocket } {
  const mockWs = ws ?? new MockWebSocket();
  const conn = new SpeechConnection(
    mockWs as any,
    config ?? { model: "speech-2.8-hd", voice_setting: { voice_id: "test" } },
  );
  return { conn, ws: mockWs };
}

// ── Helper: create a task_started message ───────────────────────────────────

function taskStartedMsg(sessionId = "sess_123"): string {
  return JSON.stringify({
    event: "task_started",
    session_id: sessionId,
    base_resp: { status_code: 0 },
  });
}

function taskContinuedMsg(
  hexAudio: string,
  isFinal: boolean,
  extraInfo?: Record<string, unknown>,
): string {
  return JSON.stringify({
    event: "task_continued",
    data: { audio: hexAudio },
    base_resp: { status_code: 0 },
    is_final: isFinal,
    extra_info: extraInfo ?? {
      audio_length: 1.0,
      audio_sample_rate: 24000,
      audio_format: "mp3",
      audio_size: 100,
    },
  });
}

function taskFailedMsg(
  message = "Something went wrong",
  code = 1000,
  traceId = "trace_001",
): string {
  return JSON.stringify({
    event: "task_failed",
    message,
    trace_id: traceId,
    base_resp: { status_code: code },
  });
}

function taskFinishedMsg(): string {
  return JSON.stringify({
    event: "task_finished",
    base_resp: { status_code: 0 },
  });
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
        voiceSetting: { voiceId: "male-qn-qingse" },
      });

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith("POST", "/v1/t2a_v2", {
        json: {
          model: "speech-2.8-hd",
          text: "Hello world",
          stream: false,
          output_format: "hex",
          voice_setting: { voice_id: "male-qn-qingse" },
        },
      });

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
        voiceSetting: { voiceId: "female-tianmei" },
        audioSetting: { sampleRate: 24000, format: "wav" },
        languageBoost: "en",
        voiceModify: { pitch: 1.1 },
        pronunciationDict: { hello: "HH EH L OW" },
        timbreWeights: [{ voiceId: "v1", weight: 0.5 }],
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
        voiceSetting: { voiceId: "male-qn-qingse" },
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
        voiceSetting: { voiceId: "male-qn-qingse" },
      });

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith("POST", "/v1/t2a_async_v2", {
        json: {
          model: "speech-2.8-hd",
          text: "A very long text to synthesize.",
          voice_setting: { voice_id: "male-qn-qingse" },
        },
      });
      expect(result).toEqual(response);
    });

    it("supports textFileId as input instead of text", async () => {
      mockClient.request.mockResolvedValue({ task_id: "task_002" });

      await speech.asyncCreate({
        textFileId: 12345,
        voiceSetting: { voiceId: "male-qn-qingse" },
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
        voiceSetting: { voiceId: "v1" },
        audioSetting: { sampleRate: 24000 },
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
      expect(mockClient.request).toHaveBeenCalledWith("GET", "/v1/query/t2a_async_query_v2", {
        params: { task_id: "task_001" },
      });
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
        fileId: "file_200",
        bytes: 50000,
        createdAt: 1700000000,
        filename: "output.mp3",
        purpose: "t2a_async",
        downloadUrl: "https://cdn.minimax.io/files/file_200",
      });

      const result = await speech.asyncGenerate({
        text: "Long text to synthesize.",
        voiceSetting: { voiceId: "male-qn-qingse" },
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
        fileId: "file_300",
        bytes: 1000,
        createdAt: 1700000000,
        filename: "out.mp3",
        purpose: "t2a_async",
        downloadUrl: "https://cdn.minimax.io/files/file_300",
      });

      await speech.asyncGenerate({
        text: "Test",
        voiceSetting: { voiceId: "v1" },
      });

      // The pollTask was called; it would use client.pollInterval (5) and
      // client.pollTimeout (600) as defaults. Just verify no error was thrown
      // and the result was returned.
      expect(mockClient.files.retrieve).toHaveBeenCalledWith("file_300");
    });
  });

  // ── connect() — tested via integration tests (dynamic import makes unit mocking flaky)

  // ── SpeechConnection._start() ─────────────────────────────────────────

  describe("SpeechConnection._start()", () => {
    it("sends task_start and resolves on task_started", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("message", taskStartedMsg("sess_xyz"));

      await startPromise;

      expect(conn.sessionId).toBe("sess_xyz");

      const sentMsg = JSON.parse(ws.send.mock.calls[0]![0] as string);
      expect(sentMsg.event).toBe("task_start");
      expect(sentMsg.model).toBe("speech-2.8-hd");
    });

    it("rejects on task_failed during start", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      // task_failed with status_code 0 in base_resp won't trigger raiseForStatus,
      // but the event handler checks event === "task_failed" directly.
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_failed",
          message: "Model not available",
          trace_id: "trace_fail",
          base_resp: { status_code: 0 },
        }),
      );

      await expect(startPromise).rejects.toThrow(MiniMaxError);
      await expect(startPromise).rejects.toThrow("Model not available");
    });

    it("rejects on WebSocket close during start", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("close");

      await expect(startPromise).rejects.toThrow("WebSocket closed during task_start");
    });

    it("rejects on WebSocket error during start", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("error", new Error("Network timeout"));

      await expect(startPromise).rejects.toThrow("Network timeout");
    });

    it("rejects if message has non-zero status_code (raiseForStatus)", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      // raiseForStatus will throw before the event check
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_started",
          session_id: "sess_err",
          base_resp: { status_code: 1004, status_msg: "Auth failed" },
          trace_id: "trace_auth",
        }),
      );

      await expect(startPromise).rejects.toThrow("Auth failed");
    });

    it("uses fallback message when task_failed has no message or base_resp", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      // No message, no trace_id, no base_resp at all
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_failed",
        }),
      );

      const err: MiniMaxError = await startPromise.catch((e: MiniMaxError) => e);
      expect(err).toBeInstanceOf(MiniMaxError);
      expect(err.message).toBe("WebSocket task_start failed");
      expect(err.code).toBe(0);
      expect(err.traceId).toBe("");
    });

    it("ignores unrecognized events during start", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      // Send an unrecognized event first
      ws.emit(
        "message",
        JSON.stringify({
          event: "some_other_event",
          base_resp: { status_code: 0 },
        }),
      );
      // Then send the expected task_started
      ws.emit("message", taskStartedMsg("sess_after_ignored"));

      await startPromise;
      expect(conn.sessionId).toBe("sess_after_ignored");
    });
  });

  // ── SpeechConnection.send() ────────────────────────────────────────────

  describe("SpeechConnection.send()", () => {
    it("sends task_continue and returns AudioResponse on is_final", async () => {
      const { conn, ws } = createConnection();
      // Manually set started state
      conn.sessionId = "sess_001";

      const audioHex = Buffer.from("hello audio").toString("hex");
      const sendPromise = conn.send("Hello!");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit(
        "message",
        taskContinuedMsg(audioHex, true, {
          audio_length: 2.5,
          audio_sample_rate: 24000,
          audio_format: "mp3",
          audio_size: 200,
        }),
      );

      const result = await sendPromise;

      expect(result).toBeInstanceOf(AudioResponse);
      expect(result.data).toEqual(Buffer.from("hello audio"));
      expect(result.duration).toBe(2.5);
      expect(result.sampleRate).toBe(24000);
      expect(result.format).toBe("mp3");
      expect(result.size).toBe(200);

      const sentMsg = JSON.parse(ws.send.mock.calls[0]![0] as string);
      expect(sentMsg.event).toBe("task_continue");
      expect(sentMsg.text).toBe("Hello!");
    });

    it("accumulates multiple chunks before is_final", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const hex1 = Buffer.from("part1").toString("hex");
      const hex2 = Buffer.from("part2").toString("hex");

      const sendPromise = conn.send("Multi-chunk text");

      await new Promise((r) => setTimeout(r, 0));

      // First chunk (not final)
      ws.emit("message", taskContinuedMsg(hex1, false));

      // Second chunk (final)
      ws.emit(
        "message",
        taskContinuedMsg(hex2, true, {
          audio_length: 3.0,
          audio_sample_rate: 24000,
          audio_format: "mp3",
          audio_size: 300,
        }),
      );

      const result = await sendPromise;

      // Combined audio from both chunks
      const expected = Buffer.concat([Buffer.from("part1"), Buffer.from("part2")]);
      expect(result.data).toEqual(expected);
    });

    it("throws if connection is closed", async () => {
      const { conn } = createConnection();
      conn.sessionId = "sess_001";

      // Simulate closing
      await simulateClose(conn);

      await expect(conn.send("Hello")).rejects.toThrow("SpeechConnection is already closed.");
    });

    it("rejects on task_failed during send", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const sendPromise = conn.send("Fail me");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_failed",
          message: "Synthesis error",
          trace_id: "trace_fail",
          base_resp: { status_code: 0 },
        }),
      );

      await expect(sendPromise).rejects.toThrow(MiniMaxError);
      await expect(sendPromise).rejects.toThrow("Synthesis error");
    });

    it("rejects on WebSocket close during send", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const sendPromise = conn.send("Hello");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("close");

      await expect(sendPromise).rejects.toThrow("WebSocket closed unexpectedly");
    });

    it("rejects on WebSocket error during send", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const sendPromise = conn.send("Hello");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("error", new Error("Socket broken"));

      await expect(sendPromise).rejects.toThrow("Socket broken");
    });

    it("handles chunk with no audio data gracefully", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const sendPromise = conn.send("Empty chunk");

      await new Promise((r) => setTimeout(r, 0));
      // Chunk with no audio field
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_continued",
          data: {},
          base_resp: { status_code: 0 },
          is_final: true,
          extra_info: {
            audio_length: 0,
            audio_sample_rate: 24000,
            audio_format: "mp3",
            audio_size: 0,
          },
        }),
      );

      const result = await sendPromise;
      expect(result).toBeInstanceOf(AudioResponse);
      expect(result.data).toEqual(Buffer.alloc(0));
    });

    it("rejects on non-zero status code in continued message", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const sendPromise = conn.send("Bad response");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_continued",
          data: { audio: "aabb" },
          base_resp: { status_code: 1042, status_msg: "Invalid parameter" },
          trace_id: "trace_inv",
          is_final: false,
        }),
      );

      // parseWSMessage will call raiseForStatus which throws
      await expect(sendPromise).rejects.toThrow("Invalid parameter");
    });

    it("uses fallback message when task_failed has no message or base_resp", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const sendPromise = conn.send("No message");

      await new Promise((r) => setTimeout(r, 0));
      // No message, no trace_id, no base_resp
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_failed",
        }),
      );

      const err: MiniMaxError = await sendPromise.catch((e: MiniMaxError) => e);
      expect(err).toBeInstanceOf(MiniMaxError);
      expect(err.message).toBe("WebSocket task_continue failed");
      expect(err.code).toBe(0);
      expect(err.traceId).toBe("");
    });

    it("ignores non-continued non-failed events and keeps waiting", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const audioHex = Buffer.from("after-ignore").toString("hex");
      const sendPromise = conn.send("Ignore test");

      await new Promise((r) => setTimeout(r, 0));
      // Unrecognized event -- should be ignored
      ws.emit(
        "message",
        JSON.stringify({
          event: "some_unknown_event",
          base_resp: { status_code: 0 },
        }),
      );
      // Then the real final chunk
      ws.emit("message", taskContinuedMsg(audioHex, true));

      const result = await sendPromise;
      expect(result.data).toEqual(Buffer.from("after-ignore"));
    });

    it("collects extra_info from last chunk that has it", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const hex = Buffer.from("data").toString("hex");
      const sendPromise = conn.send("Extra info");

      await new Promise((r) => setTimeout(r, 0));
      // First chunk without extra_info
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_continued",
          data: { audio: hex },
          base_resp: { status_code: 0 },
          is_final: false,
        }),
      );
      // Final chunk with extra_info
      ws.emit(
        "message",
        taskContinuedMsg(hex, true, {
          audio_length: 5.0,
          audio_sample_rate: 48000,
          audio_format: "wav",
          audio_size: 500,
        }),
      );

      const result = await sendPromise;
      expect(result.duration).toBe(5.0);
      expect(result.sampleRate).toBe(48000);
    });
  });

  // ── SpeechConnection.sendStream() ──────────────────────────────────────

  describe("SpeechConnection.sendStream()", () => {
    it("yields decoded audio chunks as they arrive", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const hex1 = Buffer.from("stream-part1").toString("hex");
      const hex2 = Buffer.from("stream-part2").toString("hex");

      const gen = conn.sendStream("Stream me");

      // Emit chunks after the generator starts listening
      process.nextTick(() => {
        ws.emit("message", taskContinuedMsg(hex1, false));
        ws.emit("message", taskContinuedMsg(hex2, true));
      });

      const chunks: Buffer[] = [];
      for await (const chunk of gen) {
        chunks.push(chunk);
      }

      expect(chunks).toHaveLength(2);
      expect(chunks[0]).toEqual(Buffer.from("stream-part1"));
      expect(chunks[1]).toEqual(Buffer.from("stream-part2"));

      const sentMsg = JSON.parse(ws.send.mock.calls[0]![0] as string);
      expect(sentMsg.event).toBe("task_continue");
      expect(sentMsg.text).toBe("Stream me");
    });

    it("throws if connection is closed", async () => {
      const { conn } = createConnection();
      conn.sessionId = "sess_001";

      await simulateClose(conn);

      await expect(async () => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        for await (const _ of conn.sendStream("Hello")) {
          // should not reach here
        }
      }).rejects.toThrow("SpeechConnection is already closed.");
    });

    it("throws on task_failed during streaming", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const gen = conn.sendStream("Fail stream");

      process.nextTick(() => {
        ws.emit(
          "message",
          JSON.stringify({
            event: "task_failed",
            message: "Stream synthesis error",
            trace_id: "trace_sf",
            base_resp: { status_code: 0 },
          }),
        );
      });

      await expect(async () => {
        for await (const _ of gen) {
          // should throw
        }
      }).rejects.toThrow("Stream synthesis error");
    });

    it("throws on WebSocket close during streaming", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const gen = conn.sendStream("Close stream");

      process.nextTick(() => {
        ws.emit("close");
      });

      await expect(async () => {
        for await (const _ of gen) {
          // should throw
        }
      }).rejects.toThrow("WebSocket closed unexpectedly");
    });

    it("throws on WebSocket error during streaming", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const gen = conn.sendStream("Error stream");

      process.nextTick(() => {
        ws.emit("error", new Error("Socket error during stream"));
      });

      await expect(async () => {
        for await (const _ of gen) {
          // should throw
        }
      }).rejects.toThrow("Socket error during stream");
    });

    it("handles chunk with no audio gracefully (no yield, just continues)", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const hex1 = Buffer.from("only-chunk").toString("hex");
      const gen = conn.sendStream("Sparse stream");

      process.nextTick(() => {
        // Chunk with no audio data (empty)
        ws.emit(
          "message",
          JSON.stringify({
            event: "task_continued",
            data: {},
            base_resp: { status_code: 0 },
            is_final: false,
          }),
        );
        // Then a real chunk that is final
        ws.emit("message", taskContinuedMsg(hex1, true));
      });

      const chunks: Buffer[] = [];
      for await (const chunk of gen) {
        chunks.push(chunk);
      }

      // Only the chunk with actual audio is yielded
      expect(chunks).toHaveLength(1);
      expect(chunks[0]).toEqual(Buffer.from("only-chunk"));
    });

    it("throws on non-zero status code in streamed message", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const gen = conn.sendStream("Bad status");

      process.nextTick(() => {
        ws.emit(
          "message",
          JSON.stringify({
            event: "task_continued",
            data: { audio: "aabb" },
            base_resp: { status_code: 1000, status_msg: "Server error" },
            trace_id: "trace_se",
            is_final: false,
          }),
        );
      });

      await expect(async () => {
        for await (const _ of gen) {
          // should throw
        }
      }).rejects.toThrow("Server error");
    });

    it("uses fallback message for task_failed without message or base_resp during streaming", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const gen = conn.sendStream("No msg fail");

      process.nextTick(() => {
        // No message, no trace_id, no base_resp
        ws.emit(
          "message",
          JSON.stringify({
            event: "task_failed",
          }),
        );
      });

      try {
        for await (const _ of gen) {
          // should throw
        }
        expect.unreachable("Should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(MiniMaxError);
        expect((err as MiniMaxError).message).toBe("WebSocket task_continue failed");
        expect((err as MiniMaxError).code).toBe(0);
        expect((err as MiniMaxError).traceId).toBe("");
      }
    });

    it("cleans up listeners in the finally block", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const hex = Buffer.from("data").toString("hex");
      const gen = conn.sendStream("Cleanup test");

      process.nextTick(() => {
        ws.emit("message", taskContinuedMsg(hex, true));
      });

      for await (const _ of gen) {
        // consume
      }

      // After the generator completes, production listeners should be cleaned up.
      // Only the safety no-op error listener from MockWebSocket remains.
      expect(ws.listenerCount("message")).toBe(0);
      expect(ws.listenerCount("close")).toBe(0);
      expect(ws.listenerCount("error")).toBe(0);
    });
  });

  // ── SpeechConnection.close() ──────────────────────────────────────────

  describe("SpeechConnection.close()", () => {
    it("sends task_finish and waits for task_finished", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("message", taskFinishedMsg());

      await closePromise;

      const sentMsg = JSON.parse(ws.send.mock.calls[0]![0] as string);
      expect(sentMsg.event).toBe("task_finish");
      expect(ws.close).toHaveBeenCalled();
    });

    it("resolves on task_failed response during close", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      // task_failed with status_code 0 doesn't trigger raiseForStatus
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_failed",
          base_resp: { status_code: 0 },
        }),
      );

      await closePromise;
      expect(ws.close).toHaveBeenCalled();
    });

    it("is idempotent (calling twice is safe)", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("message", taskFinishedMsg());

      await closePromise;

      // Second call should return immediately
      await conn.close();

      // send should only have been called once (from the first close)
      expect(ws.send).toHaveBeenCalledTimes(1);
    });

    it("resolves after 5-second timeout if no response", async () => {
      vi.useFakeTimers();
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      // Advance past the 5-second timeout
      await vi.advanceTimersByTimeAsync(5100);

      await closePromise;
      expect(ws.close).toHaveBeenCalled();

      vi.useRealTimers();
    });

    it("handles ws.send throwing (connection already gone)", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      ws.send.mockImplementation(() => {
        throw new Error("WebSocket is not open");
      });

      // Should not throw even if send fails
      await conn.close();
      expect(ws.close).toHaveBeenCalled();
    });

    it("handles ws.close throwing", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      ws.close.mockImplementation(() => {
        throw new Error("Already closed");
      });

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      ws.emit("message", taskFinishedMsg());

      // Should not throw even if ws.close() throws
      await closePromise;
    });

    it("resolves when parseWSMessage throws during close", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      // Send invalid JSON to trigger parse error in the catch block
      ws.emit("message", "not valid json");

      await closePromise;
      expect(ws.close).toHaveBeenCalled();
    });

    it("resolves when message has non-zero status_code during close", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      // raiseForStatus will throw but the catch in close() swallows it
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_finished",
          base_resp: { status_code: 1000, status_msg: "Server error" },
        }),
      );

      await closePromise;
      expect(ws.close).toHaveBeenCalled();
    });

    it("ignores unrecognized events and waits for task_finished", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      // Unrecognized event -- should not resolve
      ws.emit(
        "message",
        JSON.stringify({
          event: "some_other_event",
          base_resp: { status_code: 0 },
        }),
      );
      // Now send the actual task_finished
      ws.emit("message", taskFinishedMsg());

      await closePromise;
      expect(ws.close).toHaveBeenCalled();
    });

    it("ignores messages without event field during close", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const closePromise = conn.close();

      await new Promise((r) => setTimeout(r, 0));
      // Message with no event field (event ?? "" evaluates to "")
      ws.emit(
        "message",
        JSON.stringify({
          base_resp: { status_code: 0 },
        }),
      );
      // Then proper task_finished
      ws.emit("message", taskFinishedMsg());

      await closePromise;
      expect(ws.close).toHaveBeenCalled();
    });
  });

  // ── parseWSMessage() (tested indirectly via SpeechConnection) ──────────

  describe("parseWSMessage (indirect)", () => {
    it("handles Buffer input", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      // Send as Buffer instead of string
      ws.emit("message", Buffer.from(taskStartedMsg("sess_buf")));

      await startPromise;
      expect(conn.sessionId).toBe("sess_buf");
    });

    it("throws on non-zero status code in base_resp", async () => {
      const { conn, ws } = createConnection();

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_started",
          session_id: "sess_err",
          base_resp: { status_code: 1002, status_msg: "Rate limited" },
          trace_id: "trace_rl",
        }),
      );

      await expect(startPromise).rejects.toThrow("Rate limited");
    });
  });

  // ── audioResponseFromWSChunks (tested indirectly via send) ─────────────

  describe("audioResponseFromWSChunks (indirect)", () => {
    it("returns empty buffer when no hex chunks", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const sendPromise = conn.send("Empty");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit(
        "message",
        JSON.stringify({
          event: "task_continued",
          data: {},
          base_resp: { status_code: 0 },
          is_final: true,
          extra_info: {},
        }),
      );

      const result = await sendPromise;
      expect(result.data).toEqual(Buffer.alloc(0));
      expect(result.duration).toBe(0);
      expect(result.sampleRate).toBe(0);
      expect(result.format).toBe("mp3");
    });

    it("uses audio_size from extra_info when provided", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const hex = Buffer.from("test").toString("hex");
      const sendPromise = conn.send("Size test");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit(
        "message",
        taskContinuedMsg(hex, true, {
          audio_length: 1.5,
          audio_sample_rate: 16000,
          audio_format: "wav",
          audio_size: 9999,
        }),
      );

      const result = await sendPromise;
      expect(result.size).toBe(9999);
    });

    it("falls back to data length when audio_size is 0", async () => {
      const { conn, ws } = createConnection();
      conn.sessionId = "sess_001";

      const hex = Buffer.from("fallback").toString("hex");
      const sendPromise = conn.send("Fallback test");

      await new Promise((r) => setTimeout(r, 0));
      ws.emit(
        "message",
        taskContinuedMsg(hex, true, {
          audio_length: 1.0,
          audio_sample_rate: 24000,
          audio_format: "mp3",
          audio_size: 0,
        }),
      );

      const result = await sendPromise;
      // audio_size is 0, so it falls back to audioBytes.length
      expect(result.size).toBe(Buffer.from("fallback").length);
    });
  });

  // ── buildWSConfig (tested indirectly via connect) ─────────────────────

  describe("buildWSConfig (indirect)", () => {
    it("builds minimal config with just model and voiceSetting", async () => {
      const { conn, ws } = createConnection(undefined, {
        model: "speech-2.8-hd",
        voice_setting: { voice_id: "test" },
      });

      const startPromise = conn._start();

      await new Promise((r) => setTimeout(r, 0));

      const sentMsg = JSON.parse(ws.send.mock.calls[0]![0] as string);
      expect(sentMsg.event).toBe("task_start");
      expect(sentMsg.model).toBe("speech-2.8-hd");
      expect(sentMsg.voice_setting).toEqual({ voice_id: "test" });
      // No optional fields
      expect(sentMsg.audio_setting).toBeUndefined();
      expect(sentMsg.language_boost).toBeUndefined();

      ws.emit("message", taskStartedMsg());
      await startPromise;
    });
  });

  // ── convertVoiceSetting / convertAudioSetting / convertTimbreWeight ───

  describe("camelCase to snake_case converters (indirect via tts)", () => {
    it("converts voiceId to voice_id and preserves other keys", async () => {
      mockClient.request.mockResolvedValue({ data: { audio: "" } });

      await speech.tts({
        text: "Test",
        model: "speech-2.8-hd",
        voiceSetting: { voiceId: "narrator", speed: 1.2, vol: 0.8 },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.voice_setting).toEqual({
        voice_id: "narrator",
        speed: 1.2,
        vol: 0.8,
      });
    });

    it("converts sampleRate to sample_rate and preserves other keys", async () => {
      mockClient.request.mockResolvedValue({ data: { audio: "" } });

      await speech.tts({
        text: "Test",
        model: "speech-2.8-hd",
        audioSetting: { sampleRate: 48000, format: "flac", bitrate: 128 },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.audio_setting).toEqual({
        sample_rate: 48000,
        format: "flac",
        bitrate: 128,
      });
    });

    it("handles voiceSetting without voiceId", async () => {
      mockClient.request.mockResolvedValue({ data: { audio: "" } });

      await speech.tts({
        text: "Test",
        model: "speech-2.8-hd",
        voiceSetting: { speed: 1.0 },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.voice_setting).toEqual({ speed: 1.0 });
      expect(body.voice_setting).not.toHaveProperty("voice_id");
    });

    it("handles audioSetting without sampleRate", async () => {
      mockClient.request.mockResolvedValue({ data: { audio: "" } });

      await speech.tts({
        text: "Test",
        model: "speech-2.8-hd",
        audioSetting: { format: "wav" },
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.audio_setting).toEqual({ format: "wav" });
      expect(body.audio_setting).not.toHaveProperty("sample_rate");
    });

    it("converts timbreWeights voiceId to voice_id with rest spread", async () => {
      mockClient.request.mockResolvedValue({ data: { audio: "" } });

      await speech.tts({
        text: "Test",
        model: "speech-2.8-hd",
        timbreWeights: [
          { voiceId: "v1", weight: 0.6 },
          { voiceId: "v2", weight: 0.4 },
        ],
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.timbre_weights).toEqual([
        { voice_id: "v1", weight: 0.6 },
        { voice_id: "v2", weight: 0.4 },
      ]);
    });
  });
});

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Simulate closing a SpeechConnection by calling close() with a mock that
 * immediately responds with task_finished.
 */
async function simulateClose(conn: SpeechConnection): Promise<void> {
  // Access the private _ws to simulate the response
  const ws = (conn as any)._ws as MockWebSocket;
  const origSend = ws.send;
  ws.send.mockImplementation((data: string) => {
    const msg = JSON.parse(data);
    if (msg.event === "task_finish") {
      process.nextTick(() => {
        ws.emit("message", taskFinishedMsg());
      });
    } else {
      origSend(data);
    }
  });
  await conn.close();
}
