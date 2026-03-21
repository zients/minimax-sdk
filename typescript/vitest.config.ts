import { defineConfig } from "vitest/config";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import pkg from "./package.json";

// Load ../.env for integration tests (no extra dependency needed)
function loadParentEnv(): Record<string, string> {
  try {
    const content = readFileSync(resolve(__dirname, "../.env"), "utf-8");
    const env: Record<string, string> = {};
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const idx = trimmed.indexOf("=");
      if (idx === -1) continue;
      env[trimmed.slice(0, idx)] = trimmed.slice(idx + 1);
    }
    return env;
  } catch {
    return {};
  }
}

export default defineConfig({
  define: {
    __SDK_VERSION__: JSON.stringify(pkg.version),
  },
  test: {
    globals: true,
    include: ["tests/**/*.test.ts"],
    exclude: ["tests/integration/**"],
    testTimeout: 600_000,
    env: loadParentEnv(),
  },
});
