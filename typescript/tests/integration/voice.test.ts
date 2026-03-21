/**
 * Integration tests for MiniMax TypeScript SDK -- Voice module.
 *
 * Only tests list() and delete() — clone/design require pay-as-you-go.
 *
 * Run with: cd typescript && npx vitest run tests/integration/voice.test.ts
 */

import { describe, it, expect } from "vitest";
import MiniMax from "../../src/index.js";

const client = new MiniMax();

describe("Voice list()", () => {
  it("lists all voices", async () => {
    const result = await client.voice.list();

    console.log(
      `\n  system=${result.system_voice.length}  cloned=${result.voice_cloning.length}  generated=${result.voice_generation.length}`,
    );

    expect(Array.isArray(result.system_voice)).toBe(true);
    expect(Array.isArray(result.voice_cloning)).toBe(true);
    expect(Array.isArray(result.voice_generation)).toBe(true);
    expect(result.system_voice.length).toBeGreaterThan(0);
  });

  it("lists with voice_cloning filter", async () => {
    const result = await client.voice.list("voice_cloning");

    console.log(`\n  cloned=${result.voice_cloning.length}`);

    expect(Array.isArray(result.voice_cloning)).toBe(true);
  });
});
