/**
 * Integration tests for MiniMax TypeScript SDK -- Voice module.
 *
 * list() works with any account.
 * clone() and design() require a pay-as-you-go account with sufficient
 * balance — they are NOT covered by the Token Plan. These tests are
 * skipped by default.
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

  it("system voices have voice_id and description", async () => {
    const result = await client.voice.list();
    const first = result.system_voice[0]!;

    console.log(`\n  first voice: id=${first.voice_id}  name=${first.voice_name}`);

    expect(first.voice_id).toBeTruthy();
    expect(Array.isArray(first.description)).toBe(true);
  });
});

describe("Voice clone()", () => {
  // Requires pay-as-you-go balance, not covered by Token Plan
  it.skip("clones a voice from uploaded audio", async () => {
    const fileInfo = await client.voice.uploadAudio("reference.mp3");
    const result = await client.voice.clone(fileInfo.file_id, "test-clone-voice");

    expect(result.voice_id).toBe("test-clone-voice");
  });
});

describe("Voice design()", () => {
  // Requires pay-as-you-go balance, not covered by Token Plan
  it.skip("designs a voice from description", async () => {
    const result = await client.voice.design(
      "A warm, friendly male narrator",
      "Hello, welcome to our show.",
    );

    expect(result.voice_id).toBeTruthy();
    expect(result.trial_audio).toBeTruthy();
  });
});
