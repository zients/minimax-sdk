import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MiniMax } from "../src/client.js";
import { Text } from "../src/resources/text.js";
import { Speech } from "../src/resources/speech.js";
import { Voice } from "../src/resources/voice.js";
import { Video } from "../src/resources/video.js";
import { Image } from "../src/resources/image.js";
import { Music } from "../src/resources/music.js";
import { Files } from "../src/resources/files.js";

// ── Constructor: API key resolution ─────────────────────────────────────────

describe("MiniMax constructor", () => {
  const savedBaseURL = process.env.MINIMAX_BASE_URL;

  beforeEach(() => {
    vi.stubEnv("MINIMAX_API_KEY", "");
    delete process.env.MINIMAX_BASE_URL;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    if (savedBaseURL !== undefined) {
      process.env.MINIMAX_BASE_URL = savedBaseURL;
    } else {
      delete process.env.MINIMAX_BASE_URL;
    }
  });

  it("should resolve apiKey from options", () => {
    const client = new MiniMax({ apiKey: "sk-from-options" });
    // Verify by checking the internal HttpClient is created (non-null)
    expect(client._httpClient).toBeDefined();
  });

  it("should resolve apiKey from MINIMAX_API_KEY environment variable", () => {
    vi.stubEnv("MINIMAX_API_KEY", "sk-from-env");
    const client = new MiniMax();
    expect(client._httpClient).toBeDefined();
  });

  it("should prefer options.apiKey over environment variable", () => {
    vi.stubEnv("MINIMAX_API_KEY", "sk-from-env");
    // If options.apiKey is used, the client should construct successfully
    const client = new MiniMax({ apiKey: "sk-from-options" });
    expect(client._httpClient).toBeDefined();
  });

  it("should throw when no apiKey is provided and env is empty", () => {
    expect(() => new MiniMax()).toThrow("MiniMax API key is required");
  });

  it("should throw with helpful message about env variable", () => {
    expect(() => new MiniMax()).toThrow("MINIMAX_API_KEY");
  });

  it("should use default baseURL when not provided", () => {
    const client = new MiniMax({ apiKey: "sk-test" });
    expect(client._httpClient.baseURL).toBe("https://api.minimax.io");
  });

  it("should use custom baseURL from options", () => {
    const client = new MiniMax({
      apiKey: "sk-test",
      baseURL: "https://custom.api.com",
    });
    expect(client._httpClient.baseURL).toBe("https://custom.api.com");
  });

  it("should use MINIMAX_BASE_URL environment variable", () => {
    vi.stubEnv("MINIMAX_BASE_URL", "https://env-base.api.com");
    const client = new MiniMax({ apiKey: "sk-test" });
    expect(client._httpClient.baseURL).toBe("https://env-base.api.com");
  });

  it("should use default maxRetries of 2", () => {
    const client = new MiniMax({ apiKey: "sk-test" });
    expect(client._httpClient.maxRetries).toBe(2);
  });

  it("should use custom maxRetries", () => {
    const client = new MiniMax({ apiKey: "sk-test", maxRetries: 5 });
    expect(client._httpClient.maxRetries).toBe(5);
  });

  it("should use default pollInterval of 5", () => {
    const client = new MiniMax({ apiKey: "sk-test" });
    expect(client.pollInterval).toBe(5);
  });

  it("should use custom pollInterval", () => {
    const client = new MiniMax({ apiKey: "sk-test", pollInterval: 10 });
    expect(client.pollInterval).toBe(10);
  });

  it("should use default pollTimeout of 600", () => {
    const client = new MiniMax({ apiKey: "sk-test" });
    expect(client.pollTimeout).toBe(600);
  });

  it("should use custom pollTimeout", () => {
    const client = new MiniMax({ apiKey: "sk-test", pollTimeout: 300 });
    expect(client.pollTimeout).toBe(300);
  });
});

// ── Resource mounting ───────────────────────────────────────────────────────

describe("MiniMax resources", () => {
  let client: MiniMax;

  beforeEach(() => {
    vi.stubEnv("MINIMAX_API_KEY", "");
    client = new MiniMax({ apiKey: "sk-test" });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("should mount text resource as instance of Text", () => {
    expect(client.text).toBeDefined();
    expect(client.text).toBeInstanceOf(Text);
  });

  it("should mount speech resource as instance of Speech", () => {
    expect(client.speech).toBeDefined();
    expect(client.speech).toBeInstanceOf(Speech);
  });

  it("should mount voice resource as instance of Voice", () => {
    expect(client.voice).toBeDefined();
    expect(client.voice).toBeInstanceOf(Voice);
  });

  it("should mount video resource as instance of Video", () => {
    expect(client.video).toBeDefined();
    expect(client.video).toBeInstanceOf(Video);
  });

  it("should mount image resource as instance of Image", () => {
    expect(client.image).toBeDefined();
    expect(client.image).toBeInstanceOf(Image);
  });

  it("should mount music resource as instance of Music", () => {
    expect(client.music).toBeDefined();
    expect(client.music).toBeInstanceOf(Music);
  });

  it("should mount files resource as instance of Files", () => {
    expect(client.files).toBeDefined();
    expect(client.files).toBeInstanceOf(Files);
  });
});

// ── Delegated HTTP methods ──────────────────────────────────────────────────

describe("MiniMax HTTP delegation", () => {
  let client: MiniMax;
  const successBody = { base_resp: { status_code: 0 }, result: "ok" };

  beforeEach(() => {
    vi.stubEnv("MINIMAX_API_KEY", "");
    const streamBody = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data\n"));
        controller.close();
      },
    });
    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: () => Promise.resolve(successBody),
      text: () => Promise.resolve(JSON.stringify(successBody)),
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(4)),
      headers: new Headers(),
      body: streamBody,
    });

    client = new MiniMax({
      apiKey: "sk-test",
      fetch: mockFetch as unknown as typeof fetch,
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("should delegate request() to HttpClient", async () => {
    const result = await client.request("POST", "/v1/test");
    expect(result).toEqual(successBody);
  });

  it("should delegate requestAnthropic() to HttpClient", async () => {
    const result = await client.requestAnthropic("POST", "/v1/messages");
    expect(result).toEqual(successBody);
  });

  it("should delegate streamRequest()", async () => {
    const stream = await client.streamRequest("POST", "/v1/stream");
    expect(stream).toBeInstanceOf(ReadableStream);
  });

  it("should delegate streamRequestAnthropic()", async () => {
    const stream = await client.streamRequestAnthropic("POST", "/v1/messages");
    expect(stream).toBeInstanceOf(ReadableStream);
  });

  it("should delegate requestBytes()", async () => {
    const data = await client.requestBytes("GET", "/v1/files/content");
    expect(data).toBeInstanceOf(ArrayBuffer);
  });

  it("should delegate upload()", async () => {
    const result = await client.upload(
      "/v1/files/upload",
      Buffer.from("test"),
      "test.mp3",
      "voice_clone",
    );
    expect(result).toEqual(successBody);
  });
});
