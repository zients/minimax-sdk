import { describe, it, expect, vi, beforeEach } from "vitest";
import { Image } from "../../src/resources/image.js";

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

function makeImageResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: "img_001",
    data: {
      image_urls: ["https://cdn.minimax.io/img_001.png"],
    },
    metadata: {
      success_count: 1,
      failed_count: 0,
    },
    ...overrides,
  };
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Image", () => {
  let mockClient: ReturnType<typeof createMockClient>;
  let image: Image;

  beforeEach(() => {
    mockClient = createMockClient();
    image = new Image(mockClient);
  });

  // ── generate() ──────────────────────────────────────────────────────

  describe("generate()", () => {
    it("calls request with correct method, path, and body for minimal params", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      const result = await image.generate("A beautiful landscape");

      expect(mockClient.request).toHaveBeenCalledOnce();
      expect(mockClient.request).toHaveBeenCalledWith(
        "POST",
        "/v1/image_generation",
        {
          json: {
            model: "image-01",
            prompt: "A beautiful landscape",
            response_format: "url",
            n: 1,
            prompt_optimizer: false,
          },
        },
      );

      expect(result.id).toBe("img_001");
      expect(result.image_urls).toEqual(["https://cdn.minimax.io/img_001.png"]);
      expect(result.success_count).toBe(1);
      expect(result.failed_count).toBe(0);
    });

    it("uses a custom model", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      await image.generate("A cat", "image-02");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.model).toBe("image-02");
    });

    it("passes aspect_ratio option", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      await image.generate("A landscape", "image-01", {
        aspectRatio: "16:9",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.aspect_ratio).toBe("16:9");
    });

    it("passes width and height options", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      await image.generate("A portrait", "image-01", {
        width: 512,
        height: 768,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.width).toBe(512);
      expect(body.height).toBe(768);
    });

    it("passes responseFormat option", async () => {
      mockClient.request.mockResolvedValue(
        makeImageResponse({
          data: { image_base64: ["base64data=="] },
        }),
      );

      const result = await image.generate("A painting", "image-01", {
        responseFormat: "base64",
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.response_format).toBe("base64");
      expect(result.image_base64).toEqual(["base64data=="]);
    });

    it("passes seed option for reproducibility", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      await image.generate("A flower", "image-01", {
        seed: 42,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.seed).toBe(42);
    });

    it("passes n option for multiple images", async () => {
      mockClient.request.mockResolvedValue(
        makeImageResponse({
          data: {
            image_urls: [
              "https://cdn.minimax.io/img_001.png",
              "https://cdn.minimax.io/img_002.png",
              "https://cdn.minimax.io/img_003.png",
            ],
          },
          metadata: { success_count: 3, failed_count: 0 },
        }),
      );

      const result = await image.generate("Flowers", "image-01", { n: 3 });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.n).toBe(3);
      expect(result.image_urls).toHaveLength(3);
      expect(result.success_count).toBe(3);
    });

    it("passes promptOptimizer option", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      await image.generate("A sunset", "image-01", {
        promptOptimizer: true,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.prompt_optimizer).toBe(true);
    });

    it("passes subjectReference for I2I mode", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      const refs = [
        { type: "character", image_file: "https://example.com/person.jpg" },
      ];

      await image.generate("A person in a garden", "image-01", {
        subjectReference: refs,
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.subject_reference).toEqual(refs);
    });

    it("passes all options together", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      await image.generate("A scenic view", "image-02", {
        aspectRatio: "4:3",
        width: 1024,
        height: 768,
        responseFormat: "url",
        seed: 123,
        n: 2,
        promptOptimizer: true,
        subjectReference: [{ type: "scene", image_file: "https://example.com/bg.jpg" }],
      });

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body.model).toBe("image-02");
      expect(body.prompt).toBe("A scenic view");
      expect(body.aspect_ratio).toBe("4:3");
      expect(body.width).toBe(1024);
      expect(body.height).toBe(768);
      expect(body.response_format).toBe("url");
      expect(body.seed).toBe(123);
      expect(body.n).toBe(2);
      expect(body.prompt_optimizer).toBe(true);
      expect(body.subject_reference).toHaveLength(1);
    });

    it("omits optional fields when not provided", async () => {
      mockClient.request.mockResolvedValue(makeImageResponse());

      await image.generate("Simple prompt");

      const body = mockClient.request.mock.calls[0]![2].json;
      expect(body).not.toHaveProperty("aspect_ratio");
      expect(body).not.toHaveProperty("width");
      expect(body).not.toHaveProperty("height");
      expect(body).not.toHaveProperty("seed");
      expect(body).not.toHaveProperty("subject_reference");
    });

    it("handles partial failure in response", async () => {
      mockClient.request.mockResolvedValue(
        makeImageResponse({
          data: {
            image_urls: ["https://cdn.minimax.io/img_001.png"],
          },
          metadata: { success_count: 1, failed_count: 2 },
        }),
      );

      const result = await image.generate("Test", "image-01", { n: 3 });
      expect(result.success_count).toBe(1);
      expect(result.failed_count).toBe(2);
    });
  });
});
