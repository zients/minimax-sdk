import { describe, it, expect, vi, beforeEach } from "vitest";
import { Files } from "../../src/resources/files.js";

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

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Files", () => {
  let mockClient: ReturnType<typeof createMockClient>;
  let files: Files;

  beforeEach(() => {
    mockClient = createMockClient();
    files = new Files(mockClient);
  });

  // ── upload() ────────────────────────────────────────────────────────

  describe("upload()", () => {
    it("uploads a Buffer with purpose voice_clone", async () => {
      // Mock API returns snake_case
      const apiResponse = {
        file_id: "f_001",
        bytes: 2048,
        created_at: 1700000000,
        filename: "upload",
        purpose: "voice_clone",
      };
      mockClient.upload.mockResolvedValue({ file: apiResponse });

      const result = await files.upload(Buffer.from("audio data"), "voice_clone");

      expect(mockClient.upload).toHaveBeenCalledOnce();
      const callArgs = mockClient.upload.mock.calls[0]!;
      expect(callArgs[0]).toBe("/v1/files/upload");
      // callArgs[1] is the Blob
      expect(callArgs[2]).toBe("upload"); // filename for Buffer
      expect(callArgs[3]).toBe("voice_clone");

      // Parser converts to camelCase
      expect(result).toEqual({
        fileId: "f_001",
        bytes: 2048,
        createdAt: 1700000000,
        filename: "upload",
        purpose: "voice_clone",
        downloadUrl: undefined,
      });
    });

    it("uploads a Blob with purpose prompt_audio", async () => {
      const apiResponse = {
        file_id: "f_002",
        bytes: 1024,
        created_at: 1700000000,
        filename: "upload",
        purpose: "prompt_audio",
      };
      mockClient.upload.mockResolvedValue({ file: apiResponse });

      const blob = new Blob([new Uint8Array([1, 2, 3])]);
      const result = await files.upload(blob, "prompt_audio");

      expect(mockClient.upload).toHaveBeenCalledOnce();
      const callArgs = mockClient.upload.mock.calls[0]!;
      expect(callArgs[0]).toBe("/v1/files/upload");
      expect(callArgs[2]).toBe("upload"); // filename for Blob
      expect(callArgs[3]).toBe("prompt_audio");
      expect(result).toEqual({
        fileId: "f_002",
        bytes: 1024,
        createdAt: 1700000000,
        filename: "upload",
        purpose: "prompt_audio",
        downloadUrl: undefined,
      });
    });

    it("accepts t2a_async_input purpose", async () => {
      mockClient.upload.mockResolvedValue({
        file: { file_id: "f_003", bytes: 100, created_at: 0, filename: "upload", purpose: "t2a_async_input" },
      });

      const result = await files.upload(Buffer.from("text data"), "t2a_async_input");
      expect(result.purpose).toBe("t2a_async_input");
    });

    it("throws on invalid purpose", async () => {
      await expect(
        files.upload(Buffer.from("data"), "invalid_purpose"),
      ).rejects.toThrow(/Invalid upload purpose "invalid_purpose"/);

      expect(mockClient.upload).not.toHaveBeenCalled();
    });

    it("rejects unsupported purposes", async () => {
      for (const bad of ["speech", "video", "general", ""]) {
        await expect(
          files.upload(Buffer.from("x"), bad),
        ).rejects.toThrow(/Invalid upload purpose/);
      }
    });
  });

  // ── list() ──────────────────────────────────────────────────────────

  describe("list()", () => {
    it("calls request with GET and purpose param", async () => {
      // Mock API returns snake_case
      const fileList = [
        {
          file_id: "f_001",
          bytes: 2048,
          created_at: 1700000000,
          filename: "audio.wav",
          purpose: "voice_clone",
        },
        {
          file_id: "f_002",
          bytes: 1024,
          created_at: 1700000001,
          filename: "audio2.wav",
          purpose: "voice_clone",
        },
      ];
      mockClient.request.mockResolvedValue({ files: fileList });

      const result = await files.list("voice_clone");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "GET",
        "/v1/files/list",
        {
          params: { purpose: "voice_clone" },
        },
      );

      expect(result).toHaveLength(2);
      // Parser converts to camelCase
      expect(result[0]!.fileId).toBe("f_001");
      expect(result[1]!.fileId).toBe("f_002");
    });

    it("returns empty array when no files", async () => {
      mockClient.request.mockResolvedValue({});

      const result = await files.list("prompt_audio");
      expect(result).toEqual([]);
    });
  });

  // ── retrieve() ──────────────────────────────────────────────────────

  describe("retrieve()", () => {
    it("calls request with GET and file_id param", async () => {
      // Mock API returns snake_case
      const apiResponse = {
        file_id: "12345",
        bytes: 5000,
        created_at: 1700000000,
        filename: "output.mp3",
        purpose: "t2a_async",
        download_url: "https://cdn.minimax.io/files/12345",
      };
      mockClient.request.mockResolvedValue({ file: apiResponse });

      const result = await files.retrieve("12345");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "GET",
        "/v1/files/retrieve",
        {
          params: { file_id: "12345" },
        },
      );

      // Parser converts to camelCase
      expect(result).toEqual({
        fileId: "12345",
        bytes: 5000,
        createdAt: 1700000000,
        filename: "output.mp3",
        purpose: "t2a_async",
        downloadUrl: "https://cdn.minimax.io/files/12345",
      });
      expect(result.downloadUrl).toBe("https://cdn.minimax.io/files/12345");
    });

    it("passes file_id as a string in params", async () => {
      mockClient.request.mockResolvedValue({
        file: { file_id: "99999" },
      });

      await files.retrieve("99999");

      const params = mockClient.request.mock.calls[0]![2].params;
      expect(params.file_id).toBe("99999");
    });
  });

  // ── retrieveContent() ──────────────────────────────────────────────

  describe("retrieveContent()", () => {
    it("calls requestBytes with GET and file_id param", async () => {
      const arrayBuffer = new ArrayBuffer(16);
      mockClient.requestBytes.mockResolvedValue(arrayBuffer);

      const result = await files.retrieveContent("12345");

      expect(mockClient.requestBytes).toHaveBeenCalledOnce();
      expect(mockClient.requestBytes).toHaveBeenCalledWith(
        "GET",
        "/v1/files/retrieve_content",
        {
          params: { file_id: "12345" },
        },
      );

      expect(result).toBe(arrayBuffer);
    });

    it("passes file_id as a string in params", async () => {
      mockClient.requestBytes.mockResolvedValue(new ArrayBuffer(0));

      await files.retrieveContent("67890");

      const params = mockClient.requestBytes.mock.calls[0]![2].params;
      expect(params.file_id).toBe("67890");
    });
  });

  // ── delete() ────────────────────────────────────────────────────────

  describe("delete()", () => {
    it("calls request with POST, correct path, and body", async () => {
      mockClient.request.mockResolvedValue({});

      await files.delete("12345", "voice_clone");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/files/delete",
        {
          json: { file_id: 12345, purpose: "voice_clone" },
        },
      );
    });

    it("converts file_id to number in the body", async () => {
      mockClient.request.mockResolvedValue({});

      await files.delete("99999", "prompt_audio");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.file_id).toBe(99999);
      expect(typeof body.file_id).toBe("number");
    });

    it("returns void (no value)", async () => {
      mockClient.request.mockResolvedValue({});

      const result = await files.delete("100", "voice_clone");
      expect(result).toBeUndefined();
    });

    it("rejects empty string fileId", async () => {
      await expect(files.delete("", "voice_clone")).rejects.toThrow(
        'file_id must be a numeric string, got: ""',
      );
    });

    it("rejects whitespace-only fileId", async () => {
      await expect(files.delete("  ", "voice_clone")).rejects.toThrow(
        "file_id must be a numeric string",
      );
    });

    it("rejects non-numeric fileId", async () => {
      await expect(files.delete("abc", "voice_clone")).rejects.toThrow(
        "file_id must be a numeric string",
      );
    });

    it("rejects mixed alphanumeric fileId", async () => {
      await expect(files.delete("123abc", "voice_clone")).rejects.toThrow(
        "file_id must be a numeric string",
      );
    });
  });
});
