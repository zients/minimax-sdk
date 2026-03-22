import { describe, it, expect, vi } from "vitest";
import { pollTask } from "../src/polling.js";
import { MiniMaxError, PollTimeoutError } from "../src/error.js";

function createMockHttp(responses: Record<string, unknown>[]) {
  let callIndex = 0;
  return {
    request: vi.fn().mockImplementation(async () => {
      return responses[callIndex++]!;
    }),
  } as any;
}

describe("pollTask", () => {
  it("should return on Success status", async () => {
    const http = createMockHttp([{ status: "Success", file_id: "123" }]);

    const result = await pollTask(http, "/v1/query/video_generation", "task1", {
      pollInterval: 0.01,
      pollTimeout: 10,
    });

    expect(result.status).toBe("Success");
    expect(result.file_id).toBe("123");
  });

  it("should poll until Success", async () => {
    const http = createMockHttp([
      { status: "Processing" },
      { status: "Processing" },
      { status: "Success", file_id: "456" },
    ]);

    const result = await pollTask(http, "/v1/query/test", "task2", {
      pollInterval: 0.01,
      pollTimeout: 10,
    });

    expect(result.status).toBe("Success");
    expect(http.request).toHaveBeenCalledTimes(3);
  });

  it("should throw MiniMaxError on Fail status", async () => {
    const http = createMockHttp([{ status: "Fail", status_msg: "Generation failed" }]);

    await expect(
      pollTask(http, "/v1/query/test", "task3", {
        pollInterval: 0.01,
        pollTimeout: 10,
      }),
    ).rejects.toThrow(MiniMaxError);
  });

  it("should throw PollTimeoutError when deadline exceeded", async () => {
    const http = createMockHttp(Array(100).fill({ status: "Processing" }));

    await expect(
      pollTask(http, "/v1/query/test", "task4", {
        pollInterval: 0.01,
        pollTimeout: 0.02,
      }),
    ).rejects.toThrow(PollTimeoutError);
  });

  it("should pass task_id as query param", async () => {
    const http = createMockHttp([{ status: "Success" }]);

    await pollTask(http, "/v1/query/test", "my-task-id", {
      pollInterval: 0.01,
      pollTimeout: 10,
    });

    expect(http.request).toHaveBeenCalledWith("GET", "/v1/query/test", {
      params: { task_id: "my-task-id" },
    });
  });

  it("should handle Preparing and Queueing statuses", async () => {
    const http = createMockHttp([
      { status: "Preparing" },
      { status: "Queueing" },
      { status: "Processing" },
      { status: "Success", file_id: "789" },
    ]);

    const result = await pollTask(http, "/v1/query/test", "task5", {
      pollInterval: 0.01,
      pollTimeout: 10,
    });

    expect(result.status).toBe("Success");
    expect(http.request).toHaveBeenCalledTimes(4);
  });

  it("should use default poll interval and timeout", async () => {
    const http = createMockHttp([{ status: "Success" }]);

    const result = await pollTask(http, "/v1/query/test", "task6");
    expect(result.status).toBe("Success");
  });
});
