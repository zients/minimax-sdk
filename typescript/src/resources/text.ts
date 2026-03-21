/**
 * Text resource -- text generation via MiniMax's Anthropic-compatible endpoint.
 *
 * Provides both non-streaming ({@link Text.create}) and streaming
 * ({@link Text.createStream}) methods for the
 * `POST /anthropic/v1/messages` endpoint.
 */

import { APIResource } from "../resource.js";
import { MiniMaxError } from "../error.js";
import { parseSSEStream } from "../streaming.js";

// ── Content block types ─────────────────────────────────────────────────────

export interface TextBlock {
  type: "text";
  text: string;
}

export interface ToolUseBlock {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ThinkingBlock {
  type: "thinking";
  thinking: string;
  signature: string;
}

export type ContentBlock = TextBlock | ToolUseBlock | ThinkingBlock;

// ── Usage ───────────────────────────────────────────────────────────────────

export interface Usage {
  input_tokens: number;
  output_tokens: number;
}

// ── Message ─────────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  type: "message";
  role: "assistant";
  content: ContentBlock[];
  model: string;
  stop_reason: string | null;
  stop_sequence: string | null;
  usage: Usage;
}

// ── Streaming delta types ───────────────────────────────────────────────────

export interface TextDelta {
  type: "text_delta";
  text: string;
}

export interface InputJsonDelta {
  type: "input_json_delta";
  partial_json: string;
}

export interface ThinkingDelta {
  type: "thinking_delta";
  thinking: string;
}

export interface SignatureDelta {
  type: "signature_delta";
  signature: string;
}

export type Delta = TextDelta | InputJsonDelta | ThinkingDelta | SignatureDelta;

// ── Message delta ───────────────────────────────────────────────────────────

export interface MessageDelta {
  stop_reason: string | null;
  stop_sequence: string | null;
}

// ── Streaming event types ───────────────────────────────────────────────────

export interface MessageStartEvent {
  type: "message_start";
  message: Message;
}

export interface ContentBlockStartEvent {
  type: "content_block_start";
  index: number;
  content_block: ContentBlock;
}

export interface ContentBlockDeltaEvent {
  type: "content_block_delta";
  index: number;
  delta: Delta;
}

export interface ContentBlockStopEvent {
  type: "content_block_stop";
  index: number;
}

export interface MessageDeltaEvent {
  type: "message_delta";
  delta: MessageDelta;
  usage: Usage;
}

export interface MessageStopEvent {
  type: "message_stop";
}

export type StreamEvent =
  | MessageStartEvent
  | ContentBlockStartEvent
  | ContentBlockDeltaEvent
  | ContentBlockStopEvent
  | MessageDeltaEvent
  | MessageStopEvent;

// ── Request parameters ──────────────────────────────────────────────────────

export interface TextCreateParams {
  model: string;
  messages: Record<string, unknown>[];
  max_tokens: number;
  system?: string | Record<string, unknown>[];
  temperature?: number;
  top_p?: number;
  tools?: Record<string, unknown>[];
  tool_choice?: Record<string, unknown>;
  thinking?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

const MESSAGES_PATH = "/anthropic/v1/messages";

function buildMessagesBody(
  params: TextCreateParams,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: params.model,
    messages: params.messages,
    max_tokens: params.max_tokens,
  };

  if (params.system !== undefined) body.system = params.system;
  if (params.temperature !== undefined) body.temperature = params.temperature;
  if (params.top_p !== undefined) body.top_p = params.top_p;
  if (params.tools !== undefined) body.tools = params.tools;
  if (params.tool_choice !== undefined) body.tool_choice = params.tool_choice;
  if (params.thinking !== undefined) body.thinking = params.thinking;
  if (params.metadata !== undefined) body.metadata = params.metadata;

  return body;
}

// ── Text resource ───────────────────────────────────────────────────────────

/**
 * Text generation resource.
 *
 * Uses MiniMax's Anthropic-compatible endpoint to generate text responses.
 * Supports multi-turn conversations, tool use, and extended thinking.
 */
export class Text extends APIResource {
  /**
   * Create a text generation (chat completion) request.
   *
   * @param params.model - Model ID (e.g. "MiniMax-M2.7", "MiniMax-M2.5").
   * @param params.messages - Conversation history as a list of message objects
   *   with `role` ("user" or "assistant") and `content`.
   * @param params.max_tokens - Maximum number of tokens to generate.
   * @param params.system - System prompt -- either a plain string or a list of
   *   text block objects.
   * @param params.temperature - Sampling temperature in range (0, 1].
   * @param params.top_p - Nucleus sampling threshold in range (0, 1].
   * @param params.tools - Tool definitions for function calling.
   * @param params.tool_choice - Tool selection strategy (auto, any, tool, none).
   * @param params.thinking - Extended thinking configuration, e.g.
   *   `{ type: "enabled", budget_tokens: 10000 }`.
   * @param params.metadata - Request metadata (e.g. `{ user_id: "..." }`).
   * @returns A {@link Message} with the model's response content, usage
   *   statistics, and stop reason.
   */
  async create(params: TextCreateParams): Promise<Message> {
    const body = buildMessagesBody(params);

    const resp = await this._client.requestAnthropic("POST", MESSAGES_PATH, {
      json: body,
    });

    return resp as unknown as Message;
  }

  /**
   * Create a streaming text generation request.
   *
   * Yields {@link StreamEvent} objects as the model generates content.
   * Events follow the Anthropic SSE format:
   *
   *   message_start -> content_block_start -> content_block_delta* ->
   *   content_block_stop -> ... -> message_delta -> message_stop
   *
   * @example
   * ```ts
   * for await (const event of client.text.createStream({
   *   model: "MiniMax-M2.7",
   *   messages: [{ role: "user", content: "Hello" }],
   *   max_tokens: 1024,
   * })) {
   *   if (event.type === "content_block_delta") {
   *     if (event.delta.type === "text_delta") {
   *       process.stdout.write(event.delta.text);
   *     }
   *   }
   * }
   * ```
   */
  async *createStream(
    params: TextCreateParams,
  ): AsyncGenerator<StreamEvent> {
    const body = buildMessagesBody(params);
    body.stream = true;

    const stream = await this._client.streamRequestAnthropic(
      "POST",
      MESSAGES_PATH,
      { json: body },
    );

    for await (const payload of parseSSEStream(stream)) {
      yield payload as unknown as StreamEvent;
    }
  }
}
