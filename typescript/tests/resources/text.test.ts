import { describe, it, expect, vi, beforeEach } from "vitest";
import { Text } from "../../src/resources/text.js";
import type { Message, StreamEvent } from "../../src/resources/text.js";

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

/** Build a minimal raw API response (snake_case) for use as a mock response. */
function makeRawMessage(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "msg_001",
    type: "message",
    role: "assistant",
    content: [{ type: "text", text: "Hello!" }],
    model: "MiniMax-M2.7",
    stop_reason: "end_turn",
    stop_sequence: null,
    usage: { input_tokens: 10, output_tokens: 5 },
    ...overrides,
  };
}

/**
 * Create a ReadableStream<string> that yields the given lines.
 * Each line is enqueued as its own read() result.
 */
function makeSSEStream(lines: string[]): ReadableStream<string> {
  return new ReadableStream<string>({
    start(controller) {
      for (const line of lines) {
        controller.enqueue(line);
      }
      controller.close();
    },
  });
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Text", () => {
  let mockClient: ReturnType<typeof createMockClient>;
  let text: Text;

  beforeEach(() => {
    mockClient = createMockClient();
    text = new Text(mockClient);
  });

  // ── create() ────────────────────────────────────────────────────────────

  describe("create()", () => {
    it("calls requestAnthropic with correct method, path, and body", async () => {
      const rawMessage = makeRawMessage();
      mockClient.requestAnthropic.mockResolvedValue(rawMessage);

      const result = await text.create({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hello" }],
        maxTokens: 1024,
      });

      expect(mockClient.requestAnthropic).toHaveBeenCalledOnce();
      expect(mockClient.requestAnthropic).toHaveBeenCalledWith(
        "POST",
        "/anthropic/v1/messages",
        {
          json: {
            model: "MiniMax-M2.7",
            messages: [{ role: "user", content: "Hello" }],
            max_tokens: 1024,
          },
        },
      );
      // Verify parsed camelCase response
      expect(result.stopReason).toBe("end_turn");
      expect(result.stopSequence).toBeNull();
      expect(result.usage.inputTokens).toBe(10);
      expect(result.usage.outputTokens).toBe(5);
    });

    it("includes all optional params in the body", async () => {
      mockClient.requestAnthropic.mockResolvedValue(makeRawMessage());

      const tools = [{ name: "get_weather", description: "Get weather", input_schema: {} }];
      const toolChoice = { type: "auto" };
      const thinking = { type: "enabled", budget_tokens: 10000 };
      const metadata = { user_id: "test-user" };

      await text.create({
        model: "MiniMax-M2.5",
        messages: [{ role: "user", content: "What is the weather?" }],
        maxTokens: 2048,
        system: "You are a helpful assistant.",
        temperature: 0.7,
        topP: 0.9,
        tools,
        toolChoice,
        thinking,
        metadata,
      });

      const callArgs = mockClient.requestAnthropic.mock.calls[0]!;
      const body = callArgs[2].json;

      expect(body.model).toBe("MiniMax-M2.5");
      expect(body.max_tokens).toBe(2048);
      expect(body.system).toBe("You are a helpful assistant.");
      expect(body.temperature).toBe(0.7);
      expect(body.top_p).toBe(0.9);
      expect(body.tools).toEqual(tools);
      expect(body.tool_choice).toEqual(toolChoice);
      expect(body.thinking).toEqual(thinking);
      expect(body.metadata).toEqual(metadata);
    });

    it("omits optional params when they are undefined", async () => {
      mockClient.requestAnthropic.mockResolvedValue(makeRawMessage());

      await text.create({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hi" }],
        maxTokens: 256,
      });

      const body = mockClient.requestAnthropic.mock.calls[0]![2].json;

      expect(body).toEqual({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hi" }],
        max_tokens: 256,
      });
      expect(body).not.toHaveProperty("system");
      expect(body).not.toHaveProperty("temperature");
      expect(body).not.toHaveProperty("tools");
      expect(body).not.toHaveProperty("thinking");
    });

    it("returns a Message with TextBlock content", async () => {
      const rawMessage = makeRawMessage({
        content: [{ type: "text", text: "The answer is 42." }],
      });
      mockClient.requestAnthropic.mockResolvedValue(rawMessage);

      const result = await text.create({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "What is 6*7?" }],
        maxTokens: 100,
      });

      expect(result.content).toHaveLength(1);
      expect(result.content[0]!.type).toBe("text");
      expect((result.content[0] as any).text).toBe("The answer is 42.");
    });

    it("returns a Message with ToolUseBlock content", async () => {
      const rawMessage = makeRawMessage({
        content: [
          {
            type: "tool_use",
            id: "tu_001",
            name: "get_weather",
            input: { location: "Tokyo" },
          },
        ],
        stop_reason: "tool_use",
      });
      mockClient.requestAnthropic.mockResolvedValue(rawMessage);

      const result = await text.create({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Weather in Tokyo?" }],
        maxTokens: 1024,
        tools: [{ name: "get_weather", description: "Get weather", input_schema: {} }],
      });

      expect(result.stopReason).toBe("tool_use");
      expect(result.content[0]!.type).toBe("tool_use");
      const block = result.content[0] as any;
      expect(block.name).toBe("get_weather");
      expect(block.input).toEqual({ location: "Tokyo" });
    });

    it("returns a Message with ThinkingBlock content", async () => {
      const rawMessage = makeRawMessage({
        content: [
          { type: "thinking", thinking: "Let me think...", signature: "sig_abc" },
          { type: "text", text: "Done thinking." },
        ],
      });
      mockClient.requestAnthropic.mockResolvedValue(rawMessage);

      const result = await text.create({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Think about this." }],
        maxTokens: 4096,
        thinking: { type: "enabled", budget_tokens: 10000 },
      });

      expect(result.content).toHaveLength(2);
      expect(result.content[0]!.type).toBe("thinking");
      const thinkBlock = result.content[0] as any;
      expect(thinkBlock.thinking).toBe("Let me think...");
      expect(thinkBlock.signature).toBe("sig_abc");
    });

    it("handles system as an array of text block objects", async () => {
      mockClient.requestAnthropic.mockResolvedValue(makeRawMessage());

      const systemBlocks = [
        { type: "text", text: "You are helpful." },
        { type: "text", text: "Be concise." },
      ];

      await text.create({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hi" }],
        maxTokens: 100,
        system: systemBlocks,
      });

      const body = mockClient.requestAnthropic.mock.calls[0]![2].json;
      expect(body.system).toEqual(systemBlocks);
    });
  });

  // ── createStream() ──────────────────────────────────────────────────────

  describe("createStream()", () => {
    it("sets stream:true in the body", async () => {
      mockClient.streamRequestAnthropic.mockResolvedValue(
        makeSSEStream([]),
      );

      // Consume the generator
      const events: StreamEvent[] = [];
      for await (const e of text.createStream({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hello" }],
        maxTokens: 1024,
      })) {
        events.push(e);
      }

      expect(mockClient.streamRequestAnthropic).toHaveBeenCalledOnce();
      const callArgs = mockClient.streamRequestAnthropic.mock.calls[0]!;
      expect(callArgs[0]).toBe("POST");
      expect(callArgs[1]).toBe("/anthropic/v1/messages");
      expect(callArgs[2].json.stream).toBe(true);
    });

    it("yields parsed stream events with camelCase properties", async () => {
      // Raw API responses use snake_case
      const messageStart = {
        type: "message_start",
        message: makeRawMessage({ content: [] }),
      };
      const contentBlockStart = {
        type: "content_block_start",
        index: 0,
        content_block: { type: "text", text: "" },
      };
      const contentBlockDelta = {
        type: "content_block_delta",
        index: 0,
        delta: { type: "text_delta", text: "Hello" },
      };
      const contentBlockStop = {
        type: "content_block_stop",
        index: 0,
      };
      const messageDelta = {
        type: "message_delta",
        delta: { stop_reason: "end_turn", stop_sequence: null },
        usage: { input_tokens: 10, output_tokens: 5 },
      };
      const messageStop = { type: "message_stop" };

      const sseLines = [
        `data: ${JSON.stringify(messageStart)}`,
        "",
        `data: ${JSON.stringify(contentBlockStart)}`,
        "",
        `data: ${JSON.stringify(contentBlockDelta)}`,
        "",
        `data: ${JSON.stringify(contentBlockStop)}`,
        "",
        `data: ${JSON.stringify(messageDelta)}`,
        "",
        `data: ${JSON.stringify(messageStop)}`,
        "",
      ];

      mockClient.streamRequestAnthropic.mockResolvedValue(
        makeSSEStream(sseLines),
      );

      const events: StreamEvent[] = [];
      for await (const e of text.createStream({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hello" }],
        maxTokens: 1024,
      })) {
        events.push(e);
      }

      expect(events).toHaveLength(6);
      expect(events[0]!.type).toBe("message_start");
      expect(events[1]!.type).toBe("content_block_start");
      expect(events[2]!.type).toBe("content_block_delta");
      expect(events[3]!.type).toBe("content_block_stop");
      expect(events[4]!.type).toBe("message_delta");
      expect(events[5]!.type).toBe("message_stop");

      // Verify message_start has camelCase message
      const msgStart = events[0] as any;
      expect(msgStart.message.stopReason).toBe("end_turn");
      expect(msgStart.message.stopSequence).toBeNull();
      expect(msgStart.message.usage.inputTokens).toBe(10);
      expect(msgStart.message.usage.outputTokens).toBe(5);

      // Verify content_block_start has camelCase contentBlock
      const cbStart = events[1] as any;
      expect(cbStart.contentBlock).toEqual({ type: "text", text: "" });
      expect(cbStart).not.toHaveProperty("content_block");

      // Verify delta content
      const delta = events[2] as any;
      expect(delta.delta.type).toBe("text_delta");
      expect(delta.delta.text).toBe("Hello");

      // Verify message_delta has camelCase
      const msgDelta = events[4] as any;
      expect(msgDelta.delta.stopReason).toBe("end_turn");
      expect(msgDelta.delta.stopSequence).toBeNull();
      expect(msgDelta.usage.inputTokens).toBe(10);
      expect(msgDelta.usage.outputTokens).toBe(5);
    });

    it("includes all optional params in the stream body", async () => {
      mockClient.streamRequestAnthropic.mockResolvedValue(
        makeSSEStream([]),
      );

      for await (const _ of text.createStream({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hi" }],
        maxTokens: 1024,
        system: "Be brief.",
        temperature: 0.5,
        topP: 0.8,
      })) {
        // drain
      }

      const body = mockClient.streamRequestAnthropic.mock.calls[0]![2].json;
      expect(body.stream).toBe(true);
      expect(body.system).toBe("Be brief.");
      expect(body.temperature).toBe(0.5);
      expect(body.top_p).toBe(0.8);
    });

    it("parses input_json_delta to camelCase partialJson", async () => {
      const contentBlockDelta = {
        type: "content_block_delta",
        index: 0,
        delta: { type: "input_json_delta", partial_json: '{"key":' },
      };
      const messageStop = { type: "message_stop" };

      const sseLines = [
        `data: ${JSON.stringify(contentBlockDelta)}`,
        "",
        `data: ${JSON.stringify(messageStop)}`,
        "",
      ];

      mockClient.streamRequestAnthropic.mockResolvedValue(
        makeSSEStream(sseLines),
      );

      const events: StreamEvent[] = [];
      for await (const e of text.createStream({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hi" }],
        maxTokens: 100,
      })) {
        events.push(e);
      }

      expect(events).toHaveLength(2);
      const cbDelta = events[0] as any;
      expect(cbDelta.delta.type).toBe("input_json_delta");
      expect(cbDelta.delta.partialJson).toBe('{"key":');
      expect(cbDelta.delta).not.toHaveProperty("partial_json");
    });

    it("skips ping events", async () => {
      const ping = { type: "ping" };
      const messageStop = { type: "message_stop" };

      const sseLines = [
        `data: ${JSON.stringify(ping)}`,
        "",
        `data: ${JSON.stringify(messageStop)}`,
        "",
      ];

      mockClient.streamRequestAnthropic.mockResolvedValue(
        makeSSEStream(sseLines),
      );

      const events: StreamEvent[] = [];
      for await (const e of text.createStream({
        model: "MiniMax-M2.7",
        messages: [{ role: "user", content: "Hi" }],
        maxTokens: 100,
      })) {
        events.push(e);
      }

      expect(events).toHaveLength(1);
      expect(events[0]!.type).toBe("message_stop");
    });
  });
});
