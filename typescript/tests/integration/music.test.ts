/**
 * Integration tests for MiniMax TypeScript SDK -- Music module.
 *
 * Lyrics tests are lightweight. Music generation tests take 30-60+ seconds
 * and consume credits.
 *
 * Run with: cd typescript && npx vitest run tests/integration/music.test.ts
 */

import { describe, it, expect } from "vitest";
import MiniMax, { AudioResponse } from "../../src/index.js";

const SHORT_LYRICS = `[Verse]
Hello sunshine
[Chorus]
La la la`;

const client = new MiniMax();

describe("Music generateLyrics()", () => {
  it("generates full song lyrics", async () => {
    const result = await client.music.generateLyrics("write_full_song", {
      prompt: "A short happy pop song about sunshine and summer",
    });

    console.log(`\n  title=${result.songTitle}`);
    console.log(`  style=${result.styleTags}`);
    console.log(`  lyrics=${result.lyrics.slice(0, 100)}...`);

    expect(result.songTitle).toBeTruthy();
    expect(result.styleTags).toBeTruthy();
    expect(result.lyrics).toBeTruthy();
    expect(result.lyrics.length).toBeGreaterThan(10);
  });

  it("edits existing lyrics", async () => {
    const original = await client.music.generateLyrics("write_full_song", {
      prompt: "A short happy song about sunshine",
    });
    expect(original.lyrics).toBeTruthy();

    const edited = await client.music.generateLyrics("edit", {
      prompt: "Make it more energetic and add a bridge section",
      lyrics: original.lyrics,
    });

    console.log(`\n  original title=${original.songTitle}`);
    console.log(`  edited title=${edited.songTitle}`);

    expect(edited.lyrics).toBeTruthy();
    expect(edited.lyrics.length).toBeGreaterThan(10);
  });
});

describe("Music generate()", () => {
  it("generates music with URL output", async () => {
    const audio = await client.music.generate("music-2.5+", {
      lyrics: SHORT_LYRICS,
      prompt: "happy pop",
      outputFormat: "url",
    });

    console.log(`\n  duration=${audio.duration}  size=${audio.size}`);

    expect(audio.duration).toBeGreaterThan(0);
    const url = audio.data.toString("utf-8");
    expect(url).toMatch(/^https?:/);
  });

  it("streams music chunks", async () => {
    const chunks: Buffer[] = [];
    for await (const chunk of client.music.generateStream("music-2.5+", {
      lyrics: SHORT_LYRICS,
      prompt: "happy pop",
    })) {
      expect(Buffer.isBuffer(chunk)).toBe(true);
      chunks.push(chunk);
    }

    console.log(
      `\n  chunks=${chunks.length}  total=${Buffer.concat(chunks).length} bytes`,
    );

    expect(chunks.length).toBeGreaterThan(0);
    const total = Buffer.concat(chunks).length;
    expect(total).toBeGreaterThan(0);
  });

  it("generates instrumental music", async () => {
    const audio = await client.music.generate("music-2.5+", {
      prompt: "calm ambient instrumental",
      isInstrumental: true,
      outputFormat: "url",
    });

    console.log(`\n  duration=${audio.duration}`);

    expect(audio.duration).toBeGreaterThan(0);
    const url = audio.data.toString("utf-8");
    expect(url).toMatch(/^https?:/);
  });
});
