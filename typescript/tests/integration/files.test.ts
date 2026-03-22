/**
 * Integration tests for MiniMax TypeScript SDK -- Files module.
 *
 * Self-contained: uploads a synthetic MP3, tests all operations, then deletes it.
 * No token/credit consumption.
 *
 * Run with: cd typescript && npx vitest run tests/integration/files.test.ts
 */

import { describe, it, expect, type TaskContext } from "vitest";
import { writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import MiniMax from "../../src/index.js";

function makeMinimalMp3(): Buffer {
  const frameHeader = Buffer.from([0xff, 0xfb, 0x90, 0x04]);
  const frameData = Buffer.alloc(417 - 4, 0);
  const frame = Buffer.concat([frameHeader, frameData]);
  return Buffer.concat([frame, frame, frame]);
}

const client = new MiniMax();
let uploadedFileId = "";

describe("Files", () => {
  it("1. upload a synthetic MP3", async () => {
    const mp3 = makeMinimalMp3();
    const tmpPath = join(tmpdir(), `minimax-test-${Date.now()}.mp3`);

    try {
      writeFileSync(tmpPath, mp3);
      const fileInfo = await client.files.upload(tmpPath, "voice_clone");

      console.log(
        `\n  file_id=${fileInfo.fileId}  bytes=${fileInfo.bytes}  filename=${fileInfo.filename}`,
      );

      expect(fileInfo.fileId).toBeTruthy();
      expect(fileInfo.purpose).toBe("voice_clone");
      expect(fileInfo.bytes).toBeGreaterThan(0);
      expect(fileInfo.filename).toBeTruthy();
      expect(fileInfo.createdAt).toBeGreaterThan(0);

      uploadedFileId = String(fileInfo.fileId);
    } finally {
      try {
        unlinkSync(tmpPath);
      } catch {
        // ignore
      }
    }
  });

  it("2. list files contains uploaded file", async (ctx) => {
    if (!uploadedFileId) {
      ctx.skip();
      return;
    }

    const files = await client.files.list("voice_clone");

    console.log(`\n  total files: ${files.length}`);

    expect(Array.isArray(files)).toBe(true);
    expect(files.length).toBeGreaterThan(0);
    const ids = files.map((f) => String(f.fileId));
    expect(ids).toContain(uploadedFileId);
  });

  it("3. retrieve file info", async (ctx) => {
    if (!uploadedFileId) {
      ctx.skip();
      return;
    }

    const info = await client.files.retrieve(uploadedFileId);

    console.log(`\n  file_id=${info.fileId}  purpose=${info.purpose}  bytes=${info.bytes}`);

    expect(String(info.fileId)).toBe(uploadedFileId);
    expect(info.purpose).toBe("voice_clone");
    expect(info.bytes).toBeGreaterThan(0);
  });

  it("4. retrieve file content matches upload", async (ctx) => {
    if (!uploadedFileId) {
      ctx.skip();
      return;
    }

    const content = await client.files.retrieveContent(uploadedFileId);
    const downloaded = Buffer.from(content);
    const expected = makeMinimalMp3();

    console.log(`\n  downloaded=${downloaded.length} bytes  expected=${expected.length} bytes`);

    expect(downloaded.length).toBe(expected.length);
    expect(downloaded.equals(expected)).toBe(true);
  });

  it("5. delete file", async (ctx) => {
    if (!uploadedFileId) {
      ctx.skip();
      return;
    }

    await client.files.delete(uploadedFileId, "voice_clone");
    console.log(`\n  deleted file_id=${uploadedFileId}`);
  });
});
