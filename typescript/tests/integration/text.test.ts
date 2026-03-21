/**
 * Integration tests for MiniMax TypeScript SDK -- Text module.
 *
 * Tests text generation via MiniMax's Anthropic-compatible endpoint.
 * Requires MINIMAX_API_KEY environment variable.
 *
 * Run with: cd typescript && npx vitest run tests/integration/text.test.ts
 */

import { describe, it, expect } from "vitest";
import MiniMax from "../../src/index.js";
import type { Message, ContentBlock } from "../../src/index.js";

function extractText(result: Message): string {
  return result.content
    .filter((b): b is ContentBlock & { type: "text"; text: string } => b.type === "text")
    .map((b) => b.text)
    .join("");
}

function printResult(result: Message): void {
  console.log(
    `\n  model=${result.model}  stop=${result.stop_reason}  ` +
      `usage=(${result.usage.input_tokens}in/${result.usage.output_tokens}out)`,
  );
  for (let i = 0; i < result.content.length; i++) {
    const block = result.content[i]!;
    if (block.type === "thinking") {
      const preview = block.thinking.slice(0, 80).replace(/\n/g, " ");
      console.log(`  [${i}] thinking: ${preview}...`);
    } else if (block.type === "text") {
      console.log(`  [${i}] text: ${block.text}`);
    } else {
      console.log(`  [${i}] ${block.type}: ...`);
    }
  }
}

const client = new MiniMax();

describe("Text create()", () => {
  it("simple single-turn", async () => {
    const result = await client.text.create({
      model: "MiniMax-M2.7",
      messages: [{ role: "user", content: "Say hello in one word." }],
      max_tokens: 256,
    });

    printResult(result);
    expect(result.id).toBeTruthy();
    expect(result.model).toBeTruthy();
    expect(["end_turn", "max_tokens"]).toContain(result.stop_reason);
    expect(result.content.length).toBeGreaterThanOrEqual(1);
    expect(extractText(result).length).toBeGreaterThan(0);
    expect(result.usage.input_tokens).toBeGreaterThan(0);
    expect(result.usage.output_tokens).toBeGreaterThan(0);
  });

  it("with system prompt", async () => {
    const result = await client.text.create({
      model: "MiniMax-M2.7",
      messages: [
        { role: "user", content: "What is 2+2? Reply with only the number." },
      ],
      max_tokens: 256,
      system: "You are a math tutor. Answer concisely with just the number.",
    });

    printResult(result);
    const text = extractText(result);
    expect(text).toContain("4");
  });

  it("multi-turn conversation", async () => {
    const result = await client.text.create({
      model: "MiniMax-M2.7",
      messages: [
        { role: "user", content: "My name is Alice." },
        { role: "assistant", content: "Hello Alice!" },
        { role: "user", content: "What is my name?" },
      ],
      max_tokens: 256,
    });

    printResult(result);
    const text = extractText(result).toLowerCase();
    expect(text).toContain("alice");
  });

  it("with temperature", async () => {
    const result = await client.text.create({
      model: "MiniMax-M2.7",
      messages: [{ role: "user", content: "Say yes." }],
      max_tokens: 8,
      temperature: 0.1,
    });

    printResult(result);
    expect(["end_turn", "max_tokens"]).toContain(result.stop_reason);
  });
});

describe("Text createStream()", () => {
  it("streaming basic", async () => {
    let collected = "";
    const eventTypes = new Set<string>();

    console.log();
    for await (const event of client.text.createStream({
      model: "MiniMax-M2.7",
      messages: [{ role: "user", content: "Say hi in one word." }],
      max_tokens: 256,
    })) {
      eventTypes.add(event.type);
      if (
        event.type === "content_block_delta" &&
        event.delta.type === "text_delta"
      ) {
        collected += event.delta.text;
        process.stdout.write(event.delta.text);
      }
    }
    console.log(`\n  [stream collected: '${collected}']`);

    expect(collected.length).toBeGreaterThan(0);
    expect(eventTypes.has("message_start")).toBe(true);
    expect(eventTypes.has("message_stop")).toBe(true);
    expect(eventTypes.has("content_block_delta")).toBe(true);
  });

  it("streaming with system", async () => {
    let collected = "";

    console.log();
    for await (const event of client.text.createStream({
      model: "MiniMax-M2.7",
      messages: [
        {
          role: "user",
          content: "What is 1+1? Reply with only the number.",
        },
      ],
      max_tokens: 256,
      system: "Answer with just the number.",
    })) {
      if (
        event.type === "content_block_delta" &&
        event.delta.type === "text_delta"
      ) {
        collected += event.delta.text;
        process.stdout.write(event.delta.text);
      }
    }
    console.log(`\n  [stream collected: '${collected}']`);

    expect(collected).toContain("2");
  });
});
