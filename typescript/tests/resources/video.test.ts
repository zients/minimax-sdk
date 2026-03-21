import { describe, it, expect, vi, beforeEach } from "vitest";
import { Video } from "../../src/resources/video.js";

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
    },
  } as any;
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Video", () => {
  let mockClient: ReturnType<typeof createMockClient>;
  let video: Video;

  beforeEach(() => {
    mockClient = createMockClient();
    video = new Video(mockClient);
  });

  // ── create() ─────────────────────────────────────────────────────────

  describe("create()", () => {
    it("sends POST to /v1/video_generation with params", async () => {
      const response = { task_id: "vtask_001" };
      mockClient.request.mockResolvedValue(response);

      const result = await video.create({
        model: "MiniMax-Hailuo-2.3",
        prompt: "A sunset over the ocean",
      });

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/video_generation",
        {
          json: {
            model: "MiniMax-Hailuo-2.3",
            prompt: "A sunset over the ocean",
          },
        },
      );
      expect(result).toEqual(response);
    });

    it("passes all optional params", async () => {
      mockClient.request.mockResolvedValue({ task_id: "vtask_002" });

      await video.create({
        model: "MiniMax-Hailuo-2.3",
        prompt: "A cat playing",
        promptOptimizer: true,
        fastPretreatment: false,
        duration: 10,
        resolution: "1280x720",
        callbackUrl: "https://example.com/callback",
        firstFrameImage: "https://example.com/first.jpg",
        lastFrameImage: "https://example.com/last.jpg",
        subjectReference: [{ type: "character", image: "https://example.com/face.jpg" }],
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.prompt_optimizer).toBe(true);
      expect(body.fast_pretreatment).toBe(false);
      expect(body.duration).toBe(10);
      expect(body.resolution).toBe("1280x720");
      expect(body.callback_url).toBe("https://example.com/callback");
      expect(body.first_frame_image).toBe("https://example.com/first.jpg");
      expect(body.last_frame_image).toBe("https://example.com/last.jpg");
      expect(body.subject_reference).toHaveLength(1);
    });
  });

  // ── query() ──────────────────────────────────────────────────────────

  describe("query()", () => {
    it("sends GET with task_id param", async () => {
      const response = {
        task_id: "vtask_001",
        status: "Processing",
      };
      mockClient.request.mockResolvedValue(response);

      const result = await video.query("vtask_001");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "GET",
        "/v1/query/video_generation",
        {
          params: { task_id: "vtask_001" },
        },
      );
      expect(result).toEqual(response);
    });
  });

  // ── textToVideo() ────────────────────────────────────────────────────

  describe("textToVideo()", () => {
    function setupPollSuccess() {
      // create returns task_id
      mockClient.request.mockResolvedValueOnce({ task_id: "vtask_100" });
      // pollTask calls _httpClient.request
      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "vtask_100",
        status: "Success",
        file_id: "vfile_100",
        video_width: 1280,
        video_height: 720,
      });
      // files.retrieve returns download URL
      mockClient.files.retrieve.mockResolvedValueOnce({
        fileId: "vfile_100",
        bytes: 5000000,
        createdAt: 1700000000,
        filename: "video.mp4",
        purpose: "video_generation",
        downloadUrl: "https://cdn.minimax.io/files/vfile_100",
      });
    }

    it("creates task, polls, and returns VideoResult with download URL", async () => {
      setupPollSuccess();

      const result = await video.textToVideo(
        "A beautiful sunset",
        "MiniMax-Hailuo-2.3",
        { pollInterval: 1, pollTimeout: 10 },
      );

      expect(result.taskId).toBe("vtask_100");
      expect(result.status).toBe("Success");
      expect(result.fileId).toBe("vfile_100");
      expect(result.downloadUrl).toBe("https://cdn.minimax.io/files/vfile_100");
      expect(result.videoWidth).toBe(1280);
      expect(result.videoHeight).toBe(720);
    });

    it("uses default model and options", async () => {
      setupPollSuccess();

      await video.textToVideo("A sunset", undefined, {
        pollInterval: 1,
        pollTimeout: 10,
      });

      // Verify the create call used default model
      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.model).toBe("MiniMax-Hailuo-2.3");
      expect(body.prompt_optimizer).toBe(true);
      expect(body.fast_pretreatment).toBe(false);
      expect(body.duration).toBe(6);
    });

    it("passes through optional params", async () => {
      setupPollSuccess();

      await video.textToVideo("A sunset", "MiniMax-Hailuo-2.3", {
        promptOptimizer: false,
        fastPretreatment: true,
        duration: 10,
        resolution: "1920x1080",
        callbackUrl: "https://example.com/hook",
        pollInterval: 1,
        pollTimeout: 10,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.prompt_optimizer).toBe(false);
      expect(body.fast_pretreatment).toBe(true);
      expect(body.duration).toBe(10);
      expect(body.resolution).toBe("1920x1080");
      expect(body.callback_url).toBe("https://example.com/hook");
    });
  });

  // ── imageToVideo() ───────────────────────────────────────────────────

  describe("imageToVideo()", () => {
    it("includes first_frame_image in the body", async () => {
      mockClient.request.mockResolvedValueOnce({ task_id: "vtask_200" });
      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "vtask_200",
        status: "Success",
        file_id: "vfile_200",
        video_width: 1280,
        video_height: 720,
      });
      mockClient.files.retrieve.mockResolvedValueOnce({
        fileId: "vfile_200",
        bytes: 1000,
        createdAt: 1700000000,
        filename: "video.mp4",
        purpose: "video_generation",
        downloadUrl: "https://cdn.minimax.io/vfile_200",
      });

      const result = await video.imageToVideo(
        "https://example.com/first-frame.jpg",
        "MiniMax-Hailuo-2.3",
        {
          prompt: "A gentle animation",
          pollInterval: 1,
          pollTimeout: 10,
        },
      );

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.first_frame_image).toBe("https://example.com/first-frame.jpg");
      expect(body.prompt).toBe("A gentle animation");
      expect(result.downloadUrl).toBe("https://cdn.minimax.io/vfile_200");
    });
  });

  // ── framesToVideo() ──────────────────────────────────────────────────

  describe("framesToVideo()", () => {
    it("includes last_frame_image and optional first_frame_image", async () => {
      mockClient.request.mockResolvedValueOnce({ task_id: "vtask_300" });
      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "vtask_300",
        status: "Success",
        file_id: "vfile_300",
        video_width: 720,
        video_height: 480,
      });
      mockClient.files.retrieve.mockResolvedValueOnce({
        fileId: "vfile_300",
        bytes: 2000,
        createdAt: 1700000000,
        filename: "video.mp4",
        purpose: "video_generation",
        downloadUrl: "https://cdn.minimax.io/vfile_300",
      });

      await video.framesToVideo(
        "https://example.com/last.jpg",
        {
          firstFrameImage: "https://example.com/first.jpg",
          model: "MiniMax-Hailuo-02",
          prompt: "Smooth transition",
          pollInterval: 1,
          pollTimeout: 10,
        },
      );

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.last_frame_image).toBe("https://example.com/last.jpg");
      expect(body.first_frame_image).toBe("https://example.com/first.jpg");
      expect(body.model).toBe("MiniMax-Hailuo-02");
    });

    it("uses default model MiniMax-Hailuo-02", async () => {
      mockClient.request.mockResolvedValueOnce({ task_id: "vtask_301" });
      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "vtask_301",
        status: "Success",
        file_id: "vfile_301",
        video_width: 720,
        video_height: 480,
      });
      mockClient.files.retrieve.mockResolvedValueOnce({
        fileId: "vfile_301",
        bytes: 1000,
        createdAt: 1700000000,
        filename: "video.mp4",
        purpose: "video_generation",
        downloadUrl: "https://cdn.minimax.io/vfile_301",
      });

      await video.framesToVideo("https://example.com/last.jpg", {
        pollInterval: 1,
        pollTimeout: 10,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.model).toBe("MiniMax-Hailuo-02");
    });
  });

  // ── subjectToVideo() ─────────────────────────────────────────────────

  describe("subjectToVideo()", () => {
    it("includes subject_reference in the body", async () => {
      mockClient.request.mockResolvedValueOnce({ task_id: "vtask_400" });
      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "vtask_400",
        status: "Success",
        file_id: "vfile_400",
        video_width: 1920,
        video_height: 1080,
      });
      mockClient.files.retrieve.mockResolvedValueOnce({
        fileId: "vfile_400",
        bytes: 3000,
        createdAt: 1700000000,
        filename: "video.mp4",
        purpose: "video_generation",
        downloadUrl: "https://cdn.minimax.io/vfile_400",
      });

      const refs = [
        { type: "character", image: "https://example.com/person.jpg" },
      ];

      const result = await video.subjectToVideo(refs, {
        prompt: "A person walking in a park",
        model: "S2V-01",
        pollInterval: 1,
        pollTimeout: 10,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.subject_reference).toEqual(refs);
      expect(body.model).toBe("S2V-01");
      expect(body.prompt).toBe("A person walking in a park");
      expect(result.videoWidth).toBe(1920);
      expect(result.videoHeight).toBe(1080);
    });

    it("uses default model S2V-01", async () => {
      mockClient.request.mockResolvedValueOnce({ task_id: "vtask_401" });
      mockClient._httpClient.request.mockResolvedValueOnce({
        task_id: "vtask_401",
        status: "Success",
        file_id: "vfile_401",
        video_width: 720,
        video_height: 480,
      });
      mockClient.files.retrieve.mockResolvedValueOnce({
        fileId: "vfile_401",
        bytes: 1000,
        createdAt: 1700000000,
        filename: "video.mp4",
        purpose: "video_generation",
        downloadUrl: "https://cdn.minimax.io/vfile_401",
      });

      await video.subjectToVideo(
        [{ type: "character", image: "https://example.com/face.jpg" }],
        { pollInterval: 1, pollTimeout: 10 },
      );

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.model).toBe("S2V-01");
    });
  });
});
