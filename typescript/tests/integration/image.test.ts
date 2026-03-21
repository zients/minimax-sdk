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
    const result = await client.image.generate(
      "A red circle on white background",
      "image-01",
      { n: 1, responseFormat: "url" },
    );

    console.log(`\n  id=${result.id}  success=${result.success_count}  failed=${result.failed_count}`);
    if (result.image_urls) {
      console.log(`  url=${result.image_urls[0]?.slice(0, 80)}...`);
    }

    expect(result.image_urls).not.toBeNull();
    expect(result.image_urls!.length).toBe(1);
    expect(result.image_urls![0]).toMatch(/^https?:/);
    expect(result.success_count).toBeGreaterThanOrEqual(1);
  });

  it("generates multiple images", async () => {
    const result = await client.image.generate(
      "A blue square",
      "image-01",
      { n: 2 },
    );

    console.log(`\n  success=${result.success_count}  urls=${result.image_urls?.length}`);

    expect(result.image_urls).not.toBeNull();
    expect(result.image_urls!.length).toBe(2);
    expect(result.success_count).toBe(2);
  });

  it("generates with aspect ratio", async () => {
    const result = await client.image.generate(
      "A landscape panorama",
      "image-01",
      { aspectRatio: "16:9", n: 1 },
    );

    console.log(`\n  aspect_ratio=16:9  success=${result.success_count}`);

    expect(result.image_urls).not.toBeNull();
    expect(result.success_count).toBeGreaterThanOrEqual(1);
  });

  it("generates with base64 format", async () => {
    const result = await client.image.generate(
      "A green triangle",
      "image-01",
      { n: 1, responseFormat: "base64" },
    );

    console.log(`\n  format=base64  has_data=${!!result.image_base64}`);

    expect(result.image_base64).not.toBeNull();
    expect(result.image_base64!.length).toBe(1);
    expect(result.image_base64![0]!.length).toBeGreaterThan(100);
  });

  it("generates with prompt optimizer", async () => {
    const result = await client.image.generate(
      "sunset",
      "image-01",
      { n: 1, promptOptimizer: true },
    );

    console.log(`\n  prompt_optimizer=true  success=${result.success_count}`);

    expect(result.success_count).toBeGreaterThanOrEqual(1);
  });
});
