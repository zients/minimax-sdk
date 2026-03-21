/**
 * Integration tests for MiniMax TypeScript SDK -- Video module.
 *
 * Uses MiniMax-Hailuo-02 with resolution="768P" and duration=6
 * to minimize cost (4500 requests per video).
 *
 * These tests are expensive and slow (60-120s). They dynamically skip
 * on InsufficientBalanceError.
 *
 * Run with: cd typescript && npx vitest run tests/integration/video.test.ts
 */

import { describe, it, expect } from "vitest";
import MiniMax, { InsufficientBalanceError } from "../../src/index.js";

const MODEL = "MiniMax-Hailuo-02";
const PROMPT = "A simple red ball bouncing on a white background";

const client = new MiniMax();

describe("Video create + query", () => {
  it("creates a task and queries status", async (ctx) => {
    let createResp;
    try {
      createResp = await client.video.create({
        model: MODEL,
        prompt: PROMPT,
        resolution: "768P",
        duration: 6,
      });
    } catch (err) {
      if (err instanceof InsufficientBalanceError) {
        ctx.skip();
        return;
      }
      throw err;
    }

    console.log(`\n  task_id=${createResp.task_id}`);

    expect(createResp.task_id).toBeTruthy();
    const taskId = String(createResp.task_id);

    const queryResp = await client.video.query(taskId);

    console.log(`\n  status=${queryResp.status}`);

    expect(queryResp.task_id).toBeTruthy();
    expect(queryResp.status).toBeTruthy();
    expect(
      ["Preparing", "Queueing", "Processing", "Success", "Fail"],
    ).toContain(queryResp.status);
  });
});

describe("Video textToVideo", () => {
  it("full pipeline: create + poll + retrieve", async (ctx) => {
    let result;
    try {
      result = await client.video.textToVideo(PROMPT, MODEL, {
        resolution: "768P",
        duration: 6,
        pollInterval: 5,
        pollTimeout: 300,
      });
    } catch (err) {
      if (err instanceof InsufficientBalanceError) {
        ctx.skip();
        return;
      }
      throw err;
    }

    console.log(
      `\n  task_id=${result.task_id}  status=${result.status}  ` +
        `file_id=${result.file_id}  url=${result.download_url?.slice(0, 60)}...`,
    );

    expect(result.task_id).toBeTruthy();
    expect(result.status).toBeTruthy();
    expect(result.file_id).toBeTruthy();
    expect(result.download_url).toBeTruthy();
    expect(result.download_url).toMatch(/^https?:/);
  });
});
