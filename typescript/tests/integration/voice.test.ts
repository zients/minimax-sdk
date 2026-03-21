/**
 * Integration tests for MiniMax TypeScript SDK -- Voice module.
 *
 * list() works with any account.
 * clone() and design() require a pay-as-you-go account with sufficient
 * balance — they are NOT covered by the Token Plan. These tests
 * dynamically skip on InsufficientBalanceError.
 *
 * Run with: cd typescript && npx vitest run tests/integration/voice.test.ts
 */

import { describe, it, expect } from "vitest";
import { writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import MiniMax, { InsufficientBalanceError, InvalidParameterError } from "../../src/index.js";

function makeMinimalMp3(): Buffer {
  const frameHeader = Buffer.from([0xff, 0xfb, 0x90, 0x04]);
  const frameData = Buffer.alloc(417 - 4, 0);
  const frame = Buffer.concat([frameHeader, frameData]);
  return Buffer.concat([frame, frame, frame]);
}

const client = new MiniMax();
let clonedVoiceId = "";
let cloneFileId = "";

describe("Voice", () => {
  it("1. list system voices", async () => {
    const result = await client.voice.list("system");

    console.log(`\n  system=${result.system_voice.length}`);

    expect(result.system_voice).not.toBeNull();
    expect(result.system_voice.length).toBeGreaterThan(0);
    const first = result.system_voice[0]!;
    expect(first.voice_id).toBeTruthy();
    expect(first.voice_id.length).toBeGreaterThan(0);
  });

  it("2. list all voice types", async () => {
    const result = await client.voice.list("all");

    console.log(
      `\n  system=${result.system_voice.length}  cloned=${result.voice_cloning.length}  generated=${result.voice_generation.length}`,
    );

    expect(result.system_voice.length).toBeGreaterThan(0);
    expect(Array.isArray(result.voice_cloning)).toBe(true);
    expect(Array.isArray(result.voice_generation)).toBe(true);
  });

  it("3. design a voice from description", async (ctx) => {
    // Requires pay-as-you-go balance, not covered by Token Plan
    try {
      const result = await client.voice.design(
        "A warm, friendly female narrator with a calm tone",
        "Hello, this is a test of voice design.",
      );

      console.log(`\n  voice_id=${result.voice_id}  has_audio=${!!result.trial_audio}`);

      expect(result.voice_id).toBeTruthy();
      expect(result.voice_id.length).toBeGreaterThan(0);
      expect(result.trial_audio).toBeTruthy();
    } catch (err) {
      if (err instanceof InsufficientBalanceError) {
        ctx.skip();
        return;
      }
      throw err;
    }
  });

  it("4. upload audio and clone a voice", async (ctx) => {
    // Requires pay-as-you-go balance, not covered by Token Plan
    const mp3 = makeMinimalMp3();
    const tmpPath = join(tmpdir(), `minimax-voice-test-${Date.now()}.mp3`);

    try {
      writeFileSync(tmpPath, mp3);

      let fileInfo;
      try {
        fileInfo = await client.voice.uploadAudio(tmpPath, "voice_clone");
      } catch (err) {
        if (err instanceof InsufficientBalanceError) {
          ctx.skip();
          return;
        }
        throw err;
      }

      expect(fileInfo.file_id).toBeTruthy();
      cloneFileId = String(fileInfo.file_id);

      const voiceId = `test-clone-${Date.now()}`;

      try {
        const cloneResult = await client.voice.clone(fileInfo.file_id, voiceId);

        console.log(`\n  cloned voice_id=${cloneResult.voice_id}`);

        expect(cloneResult.voice_id).toBe(voiceId);
        clonedVoiceId = voiceId;
      } catch (err) {
        if (
          err instanceof InsufficientBalanceError ||
          err instanceof InvalidParameterError
        ) {
          ctx.skip();
          return;
        }
        throw err;
      }
    } finally {
      try {
        unlinkSync(tmpPath);
      } catch {
        // ignore
      }
    }
  });

  it("5. delete cloned voice", async (ctx) => {
    if (!clonedVoiceId) {
      ctx.skip();
      return;
    }

    await client.voice.delete(clonedVoiceId, "voice_cloning");
    console.log(`\n  deleted voice_id=${clonedVoiceId}`);
  });
});
