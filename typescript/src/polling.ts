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
  const intervalMs = (opts.pollInterval ?? 5) * 1000;
  const timeoutMs = (opts.pollTimeout ?? 600) * 1000;
  const deadline = Date.now() + timeoutMs;

  while (true) {
    const body = await http.request("GET", queryPath, {
      params: { task_id: taskId },
    });

    const status = String(body.status ?? "");

    if (status === "Success") {
      return body;
    }

    // FIX #5: Extract error from base_resp (matching Python), preserve code + trace_id
    if (status === "Fail") {
      const base = (body.base_resp ?? {}) as Record<string, unknown>;
      const code = Number(base.status_code ?? 0);
      const msg = String(base.status_msg ?? "Task failed");
      const traceId = String(
        body.trace_id ?? base.trace_id ?? "",
      );
      throw new MiniMaxError(msg, code, traceId);
    }

    if (!PENDING_STATUSES.has(status)) {
      // Unknown status — continue polling silently
    }

    // FIX #4: Check deadline AFTER query, BEFORE sleep (matching Python)
    if (Date.now() + intervalMs > deadline) {
      throw new PollTimeoutError(
        `Task ${taskId} did not complete within ${opts.pollTimeout ?? 600}s`,
      );
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
