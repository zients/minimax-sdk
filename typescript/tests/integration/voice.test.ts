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

    console.log(`\n  system=${result.systemVoice.length}`);

    expect(result.systemVoice).not.toBeNull();
    expect(result.systemVoice.length).toBeGreaterThan(0);
    const first = result.systemVoice[0]!;
    expect(first.voiceId).toBeTruthy();
    expect(first.voiceId.length).toBeGreaterThan(0);
  });

  it("2. list all voice types", async () => {
    const result = await client.voice.list("all");

    console.log(
      `\n  system=${result.systemVoice.length}  cloned=${result.voiceCloning.length}  generated=${result.voiceGeneration.length}`,
    );

    expect(result.systemVoice.length).toBeGreaterThan(0);
    expect(Array.isArray(result.voiceCloning)).toBe(true);
    expect(Array.isArray(result.voiceGeneration)).toBe(true);
  });

  it("3. design a voice from description", async (ctx) => {
    // Requires pay-as-you-go balance, not covered by Token Plan
    try {
      const result = await client.voice.design(
        "A warm, friendly female narrator with a calm tone",
        "Hello, this is a test of voice design.",
      );

      console.log(`\n  voiceId=${result.voiceId}  hasAudio=${!!result.trialAudio}`);

      expect(result.voiceId).toBeTruthy();
      expect(result.voiceId.length).toBeGreaterThan(0);
      expect(result.trialAudio).toBeTruthy();
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

      expect(fileInfo.fileId).toBeTruthy();
      cloneFileId = String(fileInfo.fileId);

      const voiceId = `test-clone-${Date.now()}`;

      try {
        const cloneResult = await client.voice.clone(fileInfo.fileId, voiceId);

        console.log(`\n  cloned voiceId=${cloneResult.voiceId}`);

        expect(cloneResult.voiceId).toBe(voiceId);
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
