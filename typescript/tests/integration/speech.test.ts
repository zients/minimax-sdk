/**
 * Integration tests for MiniMax TypeScript SDK -- Speech module.
 *
 * Tests TTS (sync, streaming), async create/query, and async generate.
 * WebSocket TTS is not yet implemented in the TypeScript SDK.
 *
 * Run with: cd typescript && npx vitest run tests/integration/speech.test.ts
 */

import { describe, it, expect } from "vitest";
import MiniMax, { AudioResponse } from "../../src/index.js";

const MODEL = "speech-2.8-hd";
const VOICE_SETTING = { voiceId: "English_expressive_narrator" };
const SHORT_TEXT = "Hello, this is a quick test.";

const client = new MiniMax();

describe("Speech tts()", () => {
  it("basic TTS returns AudioResponse", async () => {
    const audio = await client.speech.tts({
      text: SHORT_TEXT,
      model: MODEL,
      voiceSetting: VOICE_SETTING,
    });

    console.log(
      `\n  duration=${audio.duration}  sampleRate=${audio.sampleRate}  ` +
        `format=${audio.format}  size=${audio.size}`,
    );

    expect(audio).toBeInstanceOf(AudioResponse);
    expect(audio.data.length).toBeGreaterThan(0);
    expect(audio.duration).toBeGreaterThan(0);
    expect(audio.sampleRate).toBeGreaterThan(0);
    expect(audio.size).toBeGreaterThan(0);
    expect(audio.format).toBe("mp3");
  });

  it("TTS with voice and audio settings", async () => {
    const audio = await client.speech.tts({
      text: SHORT_TEXT,
      model: MODEL,
      voiceSetting: {
        voiceId: "English_expressive_narrator",
        speed: 1.2,
        pitch: 0,
      },
      audioSetting: {
        format: "mp3",
        sampleRate: 24000,
      },
    });

    console.log(
      `\n  duration=${audio.duration}  sampleRate=${audio.sampleRate}  size=${audio.size}`,
    );

    expect(audio).toBeInstanceOf(AudioResponse);
    expect(audio.data.length).toBeGreaterThan(0);
    expect(audio.duration).toBeGreaterThan(0);
    expect(audio.format).toBe("mp3");
  });
});

describe("Speech ttsStream()", () => {
  it("streams audio chunks", async () => {
    const chunks: Buffer[] = [];

    for await (const chunk of client.speech.ttsStream({
      text: SHORT_TEXT,
      model: MODEL,
      voiceSetting: VOICE_SETTING,
    })) {
      expect(Buffer.isBuffer(chunk)).toBe(true);
      chunks.push(chunk);
    }

    console.log(`\n  chunks=${chunks.length}  total=${Buffer.concat(chunks).length} bytes`);

    expect(chunks.length).toBeGreaterThan(0);
    const allBytes = Buffer.concat(chunks);
    expect(allBytes.length).toBeGreaterThan(0);
  });
});

describe("Speech async", () => {
  it("asyncCreate + asyncQuery", async () => {
    const createResp = await client.speech.asyncCreate({
      text: SHORT_TEXT,
      model: MODEL,
      voiceSetting: VOICE_SETTING,
    });

    console.log(`\n  task_id=${createResp.task_id}`);

    expect(createResp.task_id).toBeTruthy();

    const queryResp = await client.speech.asyncQuery(createResp.task_id);

    console.log(`\n  status=${queryResp.status}  task_id=${queryResp.task_id}`);

    expect(queryResp.task_id).toBe(createResp.task_id);
    expect(queryResp.status).toBeTruthy();
  });

  it("asyncGenerate full pipeline", async () => {
    const result = await client.speech.asyncGenerate({
      text: SHORT_TEXT,
      model: MODEL,
      voiceSetting: VOICE_SETTING,
      pollInterval: 2,
      pollTimeout: 120,
    });

    console.log(
      `\n  taskId=${result.taskId}  status=${result.status}  ` +
        `fileId=${result.fileId}  url=${result.downloadUrl?.slice(0, 60)}...`,
    );

    expect(result.taskId).toBeTruthy();
    expect(result.status).toBeTruthy();
    expect(result.fileId).toBeTruthy();
    expect(result.downloadUrl).toBeTruthy();
    expect(result.downloadUrl).toMatch(/^https?:/);
  });
});
