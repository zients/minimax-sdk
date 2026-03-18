# MiniMax Python SDK -- Deep Logic Review

**Date:** 2026-03-19
**Scope:** All source files under `python/src/minimax_sdk/`
**Reviewer:** Automated deep logic analysis

---

## Summary

The MiniMax Python SDK provides sync and async clients for speech, video, image, music, voice, and file APIs. The codebase is well-structured with a clean separation between HTTP transport, resource layers, and type definitions. However, this review identified **5 critical bugs** that will cause immediate runtime crashes in core user-facing methods, **4 high-severity issues** that can cause failures under realistic conditions, and several medium/low issues. The critical bugs are all in the "high-level convenience" methods (video generation pipeline, speech streaming, music streaming, speech async generation) -- meaning the most user-friendly entry points are entirely broken. These are masked by unit tests that mock out the exact code paths where the bugs reside.

---

## Findings

### CRITICAL-01: `Video._generate()` calls `poll_task()` with wrong signature

**Location:** `python/src/minimax_sdk/resources/video.py`, lines 132-136

**What it does:**
```python
poll_resp = poll_task(
    query_fn=lambda: self.query(task_id),
    poll_interval=interval,
    poll_timeout=timeout,
)
```

**What it should do:** `poll_task()` in `_polling.py` has the signature `poll_task(http_client, query_path, task_id, *, poll_interval, poll_timeout)`. It expects three positional args: `http_client`, `query_path`, and `task_id`. The call site passes `query_fn=` as a keyword argument, which is not a valid parameter of `poll_task`.

**Trigger:** Any call to `video.text_to_video()`, `video.image_to_video()`, `video.frames_to_video()`, or `video.subject_to_video()` will raise `TypeError: poll_task() got an unexpected keyword argument 'query_fn'`.

**Root cause:** The `poll_task` API was likely refactored from a callback-based design (accepting `query_fn`) to a path-based design (accepting `http_client + query_path + task_id`), but the call sites in `Video` were not updated.

**Same bug in async:** `AsyncVideo._generate()` at lines 426-430 passes `query_fn=lambda: self.query(task_id)` to `async_poll_task()` which also expects positional `(http_client, query_path, task_id)`.

**Masked by tests:** All video tests `@patch("minimax_sdk.resources.video.poll_task")` which replaces the real function, so the signature mismatch is never exercised.

**Fix approach:** Change to `poll_task(self._http, "/v1/query/video_generation", task_id, poll_interval=interval, poll_timeout=timeout)`.

---

### CRITICAL-02: `Video._generate()` accesses undefined `self._poll_interval` and `self._poll_timeout`

**Location:** `python/src/minimax_sdk/resources/video.py`, lines 129-130

**What it does:**
```python
interval = poll_interval if poll_interval is not None else self._poll_interval
timeout = poll_timeout if poll_timeout is not None else self._poll_timeout
```

**What it should do:** The `Video` class inherits from `SyncResource`, which only sets `self._http` and `self._client`. Neither `SyncResource` nor `Video` defines `_poll_interval` or `_poll_timeout`. The `MiniMax` client has `self.poll_interval` (without underscore prefix).

**Trigger:** Any high-level video method called without explicit `poll_interval`/`poll_timeout` will raise `AttributeError: 'Video' object has no attribute '_poll_interval'`.

**Root cause:** The resource assumes it has polling config attributes that were never initialized. The correct path is `self._client.poll_interval` and `self._client.poll_timeout`.

**Same bug in:** `AsyncVideo._generate()` (lines 423-424), `Speech.async_generate()` (lines 1117-1118), `AsyncSpeech.async_generate()` (lines 1509-1510).

**Masked by tests:** Tests manually inject `video._poll_interval = 5.0` and `video._poll_timeout = 600.0` on the mock object (see `test_video.py` line 29-30), hiding the fact that these attributes don't exist in production.

**Fix approach:** Replace `self._poll_interval` with `self._client.poll_interval` and `self._poll_timeout` with `self._client.poll_timeout`.

---

### CRITICAL-03: `Speech.async_generate()` accesses undefined `self._files`

**Location:** `python/src/minimax_sdk/resources/speech.py`, lines 1130 and 1522

**What it does:**
```python
file_info = self._files.retrieve(file_id)       # sync, line 1130
file_info = await self._files.retrieve(file_id)  # async, line 1522
```

**What it should do:** There is no `_files` attribute on `Speech`, `SyncResource`, or any parent class. The file retrieval should go through `self._client.files.retrieve(file_id)`.

**Trigger:** Any call to `speech.async_generate()` (both sync and async variants) will raise `AttributeError: 'Speech' object has no attribute '_files'`.

**Masked by tests:** Tests inject `speech._files = MagicMock()` (see `test_speech.py` line 57).

**Fix approach:** Replace `self._files.retrieve(...)` with `self._client.files.retrieve(...)`.

---

### CRITICAL-04: `Speech.tts_stream()` calls undefined `self._http.stream_request()`

**Location:** `python/src/minimax_sdk/resources/speech.py`, lines 887 and 1277

**What it does:**
```python
raw_iter = self._http.stream_request("POST", _T2A_PATH, json=body)
```

**What it should do:** The `HttpClient` and `AsyncHttpClient` classes in `_http.py` have no `stream_request` method. The available methods are `request`, `request_bytes`, and `upload`. Streaming requires direct access to the underlying `httpx.Client.stream()` context manager.

**Trigger:** Any call to `speech.tts_stream()` (sync) or `AsyncSpeech.tts_stream()` (async) will raise `AttributeError: 'HttpClient' object has no attribute 'stream_request'`.

**Root cause:** The streaming functionality was designed in the resource layer but never implemented in the HTTP transport layer.

**Fix approach:** Either add a `stream_request` method to `HttpClient`/`AsyncHttpClient`, or access the underlying client via `self._http._client.stream(...)` (as the music resource does, though see CRITICAL-05).

---

### CRITICAL-05: `Music.generate_stream()` accesses wrong attribute chain for httpx client

**Location:** `python/src/minimax_sdk/resources/music.py`, lines 226 and 358

**What it does:**
```python
with self._client._client.stream(...)   # sync, line 226
async with self._client._client.stream(...)  # async, line 358
```

**What it should do:** In the resource layer, `self._client` is the top-level `MiniMax` (or `AsyncMiniMax`) client object. `MiniMax` does not have a `_client` attribute -- it has `_http_client`. So `self._client._client` would try to access `MiniMax._client` which does not exist.

The correct chain to reach the raw httpx client is: `self._http._client` (i.e., `HttpClient._client` which is the `httpx.Client`).

**Trigger:** Any call to `music.generate_stream()` will raise `AttributeError: 'MiniMax' object has no attribute '_client'`.

**Fix approach:** Change `self._client._client.stream(...)` to `self._http._client.stream(...)`.

---

### HIGH-01: `request_bytes()` has no retry logic and raises httpx exceptions instead of MiniMaxError

**Location:** `python/src/minimax_sdk/_http.py`, lines 158-172 (sync) and 311-320 (async)

**What it does:**
```python
def request_bytes(self, method, path, **kwargs):
    response = self._client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.content
```

**What it should do:** Unlike `request()`, `request_bytes()` has:
1. No retry logic -- a transient network error immediately fails.
2. No error mapping -- raises raw `httpx.HTTPStatusError` instead of SDK-specific `MiniMaxError` subclasses.
3. No backoff for rate limiting.

**Trigger:** Used by `Files.retrieve_content()` for downloading file data. A momentary network glitch or rate limit will fail immediately with an unhandled exception type, while the same issue on other endpoints would be retried.

**Root cause:** `request_bytes()` was added as a simpler path for binary responses but wasn't given the same resilience as `request()`.

**Fix approach:** Wrap in retry logic matching `request()`, and catch/remap `httpx.HTTPStatusError` to `MiniMaxError`.

---

### HIGH-02: `async_poll_task()` uses deprecated `asyncio.get_event_loop()` which will fail without a running loop

**Location:** `python/src/minimax_sdk/_polling.py`, lines 137 and 161

**What it does:**
```python
deadline = asyncio.get_event_loop().time() + poll_timeout
# ...
if asyncio.get_event_loop().time() + poll_interval > deadline:
```

**What it should do:** `asyncio.get_event_loop()` has been deprecated since Python 3.10 and emits a `DeprecationWarning`. In Python 3.12+, calling it when there is no current running event loop raises a `DeprecationWarning` and may behave unexpectedly. Since this function is `async`, it is guaranteed to have a running loop, but the correct API is `asyncio.get_running_loop().time()` which is both cleaner and forward-compatible.

**Note:** The sync `poll_task()` correctly uses `time.monotonic()`, so there's an inconsistency between the two implementations.

**Fix approach:** Replace `asyncio.get_event_loop()` with `asyncio.get_running_loop()`.

---

### HIGH-03: Polling timeout check is off-by-one: checks *next* interval's end, not current time

**Location:** `python/src/minimax_sdk/_polling.py`, lines 92-97 (sync) and 161-166 (async)

**What it does:**
```python
if time.monotonic() + poll_interval > deadline:
    raise PollTimeoutError(...)
time.sleep(poll_interval)
```

**What it should do:** The check `now + poll_interval > deadline` means "if sleeping one more interval would exceed the deadline, fail now." This means the last successful query happens `poll_interval` seconds *before* the actual deadline. For a 600s timeout with 5s intervals, the effective timeout is ~595s.

More importantly, if the task completes on the very next poll (which would happen before the deadline), the user gets a premature timeout error. The check should be `now > deadline` (i.e., timeout only if we've *already* exceeded the deadline), then sleep for `min(poll_interval, deadline - now)`.

**Trigger:** Tasks that complete just before the nominal timeout will fail with `PollTimeoutError` even though the deadline hasn't been reached.

**Fix approach:** Change to `if time.monotonic() > deadline: raise PollTimeoutError(...)` and sleep for `min(poll_interval, max(0, deadline - time.monotonic()))`.

---

### HIGH-04: `_resolve_config` does not validate environment variable values; malformed values cause unhandled exceptions

**Location:** `python/src/minimax_sdk/client.py`, line 101

**What it does:**
```python
return cast(env_val)
```

**What it should do:** If `MINIMAX_MAX_RETRIES=abc` is set in the environment, `int("abc")` raises a raw `ValueError` with no context about which config parameter failed. Similarly for `float()` casts.

**Trigger:** Setting any numeric environment variable to a non-numeric value causes an unclear `ValueError` from `int()` or `float()`.

**Fix approach:** Wrap in try/except and raise a descriptive `ValueError` with the parameter name and expected type.

---

### MEDIUM-01: `_audio.py` `build_audio_response` uses `or` chaining on numeric fields, treating `0` as missing

**Location:** `python/src/minimax_sdk/_audio.py`, lines 125-142

**What it does:**
```python
duration: float = float(
    extra_info.get("audio_length", 0)
    or api_response.get("audio_length", 0)
    or api_response.get("duration", 0)
)
```

**Problem:** In Python, `0 or x` evaluates to `x` because `0` is falsy. If `extra_info["audio_length"]` is legitimately `0` (e.g., silence or very short audio), the code falls through to check `api_response["audio_length"]` and `api_response["duration"]`, potentially returning an incorrect non-zero value from a different field.

**Same pattern in:** `sample_rate` (line 131), `audio_size` (line 137).

**Trigger:** An API response where `extra_info.audio_length` is explicitly `0` but `api_response.duration` is some other value (e.g., from a previous request's data still in the dict).

**Fix approach:** Use explicit `is not None` checks instead of `or` chaining for numeric fields:
```python
val = extra_info.get("audio_length")
if val is None:
    val = api_response.get("audio_length")
if val is None:
    val = api_response.get("duration", 0)
duration = float(val)
```

---

### MEDIUM-02: `exceptions.TimeoutError` shadows the Python built-in `TimeoutError`

**Location:** `python/src/minimax_sdk/exceptions.py`, line 88; `python/src/minimax_sdk/__init__.py`, line 61

**Problem:** Defining `class TimeoutError(MiniMaxError)` and exporting it in `__all__` shadows the built-in `TimeoutError` exception. Users who do `from minimax_sdk import *` will lose access to the built-in `TimeoutError`, and those who do `from minimax_sdk import TimeoutError` may accidentally catch/raise the wrong type.

**Impact:** Low-to-medium. Unlikely to cause a crash, but confusing for users who expect the built-in behavior.

**Fix approach:** Rename to `ServerTimeoutError` or `MiniMaxTimeoutError` and deprecate the old name.

---

### MEDIUM-03: `files.py` `int(file_id)` casting -- fragile assumption about ID type

**Location:** `python/src/minimax_sdk/resources/files.py`, lines 90, 104, 117, 174, 188, 201

**What it does:** Every `retrieve`, `retrieve_content`, and `delete` call casts `file_id` to `int`:
```python
params={"file_id": int(file_id)}
```

**Problem:** The method signature declares `file_id: str`, but then casts to `int`. If the API ever returns non-numeric file IDs (UUIDs, hex strings, etc.), `int(file_id)` will raise `ValueError`. The `FileInfo` model even uses `coerce_numbers_to_str=True`, suggesting file IDs are sometimes returned as integers by the API and need to be stored as strings -- but the reverse conversion is fragile.

**Trigger:** If the API returns a file_id like `"file_abc123"`, the `int()` cast will crash.

**Fix approach:** Either validate at upload/retrieve time that file_id is numeric, or pass as-is if the API accepts string IDs. The cast introduces a hidden constraint that should be documented or validated explicitly.

---

### MEDIUM-04: SSE parsing silently swallows errors in `_parse_sse_line` and `_iter_sse_audio_chunks`

**Location:** `python/src/minimax_sdk/resources/music.py`, lines 120-137; `python/src/minimax_sdk/resources/speech.py`, lines 180-209

**Problem:** `json.JSONDecodeError` is caught and results in `return None` or `continue`. If the server sends malformed JSON, the SDK silently drops those events. For music/speech streaming, this means audio chunks could be silently lost with no indication to the caller.

Additionally, the SSE parsing does not handle multi-line `data:` fields (where a single event spans multiple `data:` lines that should be concatenated), which is part of the SSE specification.

**Trigger:** A malformed SSE event from the server, or server sending data in the multi-line format per the SSE spec.

**Fix approach:** At minimum, log a warning on `JSONDecodeError`. Consider implementing full SSE spec compliance with multi-line data concatenation.

---

### MEDIUM-05: WebSocket `_start()` and `close()` can hang indefinitely waiting for server response

**Location:** `python/src/minimax_sdk/resources/speech.py`
- `SpeechConnection._start()`, lines 298-306 (sync)
- `SpeechConnection.close()`, lines 462-475 (sync)
- `AsyncSpeechConnection._start()`, lines 549-563 (async)
- `AsyncSpeechConnection.close()`, lines 710-726 (async)

**Problem:** These methods contain `while True` loops that call `self._ws.recv()` waiting for a specific event (`task_started`, `task_finished`). If the server never sends that event (e.g., drops connection silently without proper close frame, or sends an unexpected event type), the loop runs forever. The sync version blocks the thread indefinitely; the async version blocks the coroutine indefinitely.

**Trigger:** Server bug, network partition without proper TCP RST, or unexpected event type from server.

**Note:** The `send()` and `send_stream()` methods have similar infinite loops but at least handle `task_failed` and `ConnectionClosed` exceptions. The `_start()` methods also handle `task_failed` but not `ConnectionClosed`.

**Fix approach:** Add a `recv` timeout or use `asyncio.wait_for()` for the async variant. Also catch `ConnectionClosed` in `_start()`.

---

### MEDIUM-06: Sync `SpeechConnection.__init__` calls `_start()` which can raise, leaking the WebSocket

**Location:** `python/src/minimax_sdk/resources/speech.py`, lines 258-287

**What it does:** The sync `SpeechConnection.__init__()` calls `self._start()` at line 287. If `_start()` raises (server error, connection drop), the constructor throws and the WebSocket `ws` object is never closed -- it was passed in but no `__del__` or cleanup path exists.

**Trigger:** Server rejects `task_start` with an error, or connection drops during handshake.

**Note:** The async variant (`AsyncSpeechConnection.__init__`) does NOT call `_start()` from `__init__` -- it's called separately in `AsyncSpeech.connect()` at line 1356. If that `_start()` fails, the `ws` is also leaked since there's no try/finally around it.

**Fix approach:** In `Speech.connect()`, wrap the `SpeechConnection` creation in try/finally that closes the raw WebSocket on failure. Same for `AsyncSpeech.connect()`.

---

### MEDIUM-07: `_resolve_config` cannot distinguish `param=0` from `param=None`

**Location:** `python/src/minimax_sdk/client.py`, line 97

**What it does:**
```python
if param is not None:
    return param
```

**Problem:** This correctly handles `0` and `""` being passed explicitly -- they're not `None`. However, it means passing `poll_interval=0.0` is valid, which would cause `time.sleep(0)` in a tight loop during polling, hammering the API with no backoff.

**Fix approach:** Add validation that numeric config values are positive where appropriate (e.g., `poll_interval > 0`, `poll_timeout > 0`, `max_retries >= 0`).

---

### LOW-01: Duplicate `_decode_audio` helper in `_base.py`

**Location:** `python/src/minimax_sdk/_base.py`, lines 46-52

**Problem:** `_base.py` defines `_decode_audio(hex_str)` which is functionally identical to `_audio.py`'s `decode_hex_audio(hex_str)`. All resource code imports from `_audio.py`. The `_base.py` helper appears unused.

**Fix approach:** Remove the dead code from `_base.py`.

---

### LOW-02: No validation that `text` or `text_file_id` is provided in `_build_async_body`

**Location:** `python/src/minimax_sdk/resources/speech.py`, lines 74-102

**Problem:** The docstring for `async_create` says "Either text or text_file_id must be provided," but neither `_build_async_body` nor `async_create` validates this. Omitting both sends a body without either field, which will fail at the API level with an opaque error.

**Fix approach:** Add a validation check: `if text is None and text_file_id is None: raise ValueError(...)`.

---

### LOW-03: `_ws_url` ignores the path component of `base_url`

**Location:** `python/src/minimax_sdk/resources/speech.py`, lines 105-113

**What it does:**
```python
def _ws_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.minimax.io"
    port_suffix = f":{parsed.port}" if parsed.port else ""
    return f"wss://{host}{port_suffix}{_WS_T2A_PATH}"
```

**Problem:** If the user sets `base_url="https://proxy.example.com/minimax"`, the `/minimax` path prefix is silently dropped in the WebSocket URL. The function always uses `/ws/v1/t2a_v2` directly on the host.

**Fix approach:** Include `parsed.path` (minus trailing slash) before `_WS_T2A_PATH`.

---

## Positive Observations

1. **Clean error hierarchy:** The exception classes in `exceptions.py` are well-designed with structured error codes, messages, and trace IDs. The `ERROR_CODE_MAP` and `RETRYABLE_CODES` pattern is solid.

2. **Retry logic in `request()`:** The HTTP retry implementation with exponential backoff and Retry-After header support is correct and well-structured.

3. **File handle safety in `files.py`:** The `_open_file` helper and the `try/finally` cleanup in `upload()` properly handle file descriptor lifecycle.

4. **Pydantic models:** The type definitions are clean, well-typed, and use `ConfigDict(coerce_numbers_to_str=True)` in `FileInfo` which is a good defensive pattern for handling API inconsistencies.

5. **WebSocket lifecycle:** The `SpeechConnection` and `AsyncSpeechConnection` classes have proper context manager support and their `close()` methods are idempotent with good error suppression.

6. **Voice list None handling:** The `_parse_voice_list` function correctly uses `(resp.get("system_voice") or [])` to handle `None` values in the API response, ensuring list comprehensions always iterate over a list.

---

## Remaining Questions

1. **Is `stream_request` planned?** The `HttpClient` has no `stream_request` method. Was this planned as part of TTS streaming but not yet implemented? The speech streaming tests appear to mock this method, so it's unclear if it ever worked.

2. **Is the polling API stable?** The signature mismatch between `poll_task()` and its call sites in Video suggests the polling API may have been recently refactored. Is there a transitional state here?

3. **File ID type contract:** The API documentation should clarify whether file IDs are always numeric. The `int()` casts in `files.py` assume so, but the `coerce_numbers_to_str` config in `FileInfo` suggests the API may return them as either type.

4. **Music SSE streaming auth:** The music `generate_stream()` method accesses the httpx client directly (bypassing the SDK's auth headers setup in `HttpClient.__init__`). Since the httpx client already has the `Authorization` header set at construction time, this works -- but if the auth mechanism ever changes (e.g., per-request tokens), the streaming paths would break.

---

## Bug Impact Matrix

| Finding | Methods Affected | Severity | Will Crash? |
|---------|-----------------|----------|-------------|
| CRITICAL-01 | All high-level video methods | CRITICAL | Yes, `TypeError` |
| CRITICAL-02 | All high-level video + speech async methods | CRITICAL | Yes, `AttributeError` |
| CRITICAL-03 | `speech.async_generate()` (both sync/async) | CRITICAL | Yes, `AttributeError` |
| CRITICAL-04 | `speech.tts_stream()` (both sync/async) | CRITICAL | Yes, `AttributeError` |
| CRITICAL-05 | `music.generate_stream()` (both sync/async) | CRITICAL | Yes, `AttributeError` |
| HIGH-01 | `files.retrieve_content()` | HIGH | On transient errors |
| HIGH-02 | All async polling | HIGH | DeprecationWarning, future breakage |
| HIGH-03 | All polled operations | HIGH | Premature timeout |
| HIGH-04 | Client init with bad env vars | HIGH | Unclear `ValueError` |

**Working methods:** `speech.tts()`, `image.generate()`, `music.generate()`, `music.generate_lyrics()`, `voice.*`, `files.upload/list/retrieve/delete`, `video.create/query` (low-level). These use the `request()` path which is solid.

**Broken methods:** All high-level convenience methods that involve polling or streaming are broken: `video.text_to_video/image_to_video/frames_to_video/subject_to_video`, `speech.tts_stream`, `speech.async_generate`, `music.generate_stream`.
