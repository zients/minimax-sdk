/**
 * Async task polling for long-running operations (video, async speech).
 *
 * Matches the Python SDK's _polling.py logic: create → poll → retrieve.
 */

import { MiniMaxError, PollTimeoutError } from "./error.js";
import type { HttpClient } from "./http.js";

const PENDING_STATUSES = new Set(["Preparing", "Queueing", "Processing"]);

export async function pollTask(
  http: HttpClient,
  queryPath: string,
  taskId: string,
  opts: {
    pollInterval?: number;
    pollTimeout?: number;
  } = {},
): Promise<Record<string, unknown>> {
  const interval = (opts.pollInterval ?? 5) * 1000;
  const timeout = (opts.pollTimeout ?? 600) * 1000;
  const deadline = Date.now() + timeout;

  while (true) {
    // Check deadline BEFORE sleep
    if (Date.now() >= deadline) {
      throw new PollTimeoutError(
        `Task ${taskId} did not complete within ${opts.pollTimeout ?? 600}s`,
      );
    }

    const body = await http.request("GET", queryPath, {
      params: { task_id: taskId },
    });

    const status = String(
      (body as Record<string, unknown>).status ?? "",
    );

    if (status === "Success") {
      return body;
    }

    if (status === "Fail") {
      const msg = String(
        (body as Record<string, unknown>).status_msg ??
          (body as Record<string, unknown>).message ??
          "Task failed",
      );
      throw new MiniMaxError(msg);
    }

    if (!PENDING_STATUSES.has(status)) {
      // Unknown status — log and continue
      console.warn(`Unknown poll status: ${status}`);
    }

    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}
