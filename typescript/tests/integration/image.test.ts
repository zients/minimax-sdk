/**
 * Integration tests for MiniMax TypeScript SDK -- Image module.
 *
 * Requires MINIMAX_API_KEY environment variable.
 *
 * Run with: cd typescript && npx vitest run tests/integration/image.test.ts
 */

import { describe, it, expect } from "vitest";
import MiniMax from "../../src/index.js";

const client = new MiniMax();

describe("Image generate()", () => {
  it("generates image with URL format", async () => {
    const result = await client.image.generate("A red circle on white background", "image-01", {
      n: 1,
      responseFormat: "url",
    });

    console.log(
      `\n  id=${result.id}  success=${result.successCount}  failed=${result.failedCount}`,
    );
    if (result.imageUrls) {
      console.log(`  url=${result.imageUrls[0]?.slice(0, 80)}...`);
    }

    expect(result.imageUrls).not.toBeNull();
    expect(result.imageUrls!.length).toBe(1);
    expect(result.imageUrls![0]).toMatch(/^https?:/);
    expect(result.successCount).toBeGreaterThanOrEqual(1);
  });

  it("generates multiple images", async () => {
    const result = await client.image.generate("A blue square", "image-01", { n: 2 });

    console.log(`\n  success=${result.successCount}  urls=${result.imageUrls?.length}`);

    expect(result.imageUrls).not.toBeNull();
    expect(result.imageUrls!.length).toBe(2);
    expect(result.successCount).toBe(2);
  });

  it("generates with aspect ratio", async () => {
    const result = await client.image.generate("A landscape panorama", "image-01", {
      aspectRatio: "16:9",
      n: 1,
    });

    console.log(`\n  aspect_ratio=16:9  success=${result.successCount}`);

    expect(result.imageUrls).not.toBeNull();
    expect(result.successCount).toBeGreaterThanOrEqual(1);
  });

  it("generates with base64 format", async () => {
    const result = await client.image.generate("A green triangle", "image-01", {
      n: 1,
      responseFormat: "base64",
    });

    console.log(`\n  format=base64  has_data=${!!result.imageBase64}`);

    expect(result.imageBase64).not.toBeNull();
    expect(result.imageBase64!.length).toBe(1);
    expect(result.imageBase64![0]!.length).toBeGreaterThan(100);
  });

  it("generates with prompt optimizer", async () => {
    const result = await client.image.generate("sunset", "image-01", {
      n: 1,
      promptOptimizer: true,
    });

    console.log(`\n  prompt_optimizer=true  success=${result.successCount}`);

    expect(result.successCount).toBeGreaterThanOrEqual(1);
  });
});
