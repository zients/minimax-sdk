# MiniMax SDK Design Spec

> Date: 2026-03-18

## Overview

A Python SDK (`minimax-sdk`) wrapping MiniMax's multimodal APIs: Speech, Voice, Video, Image, Music, and File management. Text generation is handled via the Anthropic SDK with `base_url="https://api.minimax.io/anthropic"` and is not part of this SDK.

TypeScript version will follow in the same monorepo.

## Decisions

| Decision | Choice |
|----------|--------|
| Language | Python first, TypeScript later |
| Package name | `minimax-sdk` (`from minimax_sdk import MiniMax`) |
| Architecture | Base Resource pattern (inheritance) |
| API style | Resource-oriented (`client.video.generate()`) |
| Async tasks | Auto polling (create → poll → download) |
| Hex audio | Auto decode to `bytes` |
| Client | Sync `MiniMax` + Async `AsyncMiniMax` |
| Errors | Custom exception hierarchy |
| HTTP client | httpx |
| Config | Environment variables (no python-dotenv) |

---

## §1 Project Structure

```
minimax-sdk/
├── .env.example
├── .gitignore
├── README.md
├── docs/
│   ├── specs/
│   ├── api-reference/
│   └── guides/
├── python/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/
│   │   └── minimax_sdk/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       ├── _base.py
│   │       ├── _http.py
│   │       ├── _polling.py
│   │       ├── _audio.py
│   │       ├── exceptions.py
│   │       ├── resources/
│   │       │   ├── __init__.py
│   │       │   ├── speech.py
│   │       │   ├── voice.py
│   │       │   ├── video.py
│   │       │   ├── image.py
│   │       │   ├── music.py
│   │       │   └── files.py
│   │       └── types/
│   │           ├── __init__.py
│   │           ├── speech.py
│   │           ├── voice.py
│   │           ├── video.py
│   │           ├── image.py
│   │           ├── music.py
│   │           └── files.py
│   └── tests/
└── typescript/
```

---

## §2 Client Design

### Initialization

```python
from minimax_sdk import MiniMax, AsyncMiniMax

client = MiniMax()                    # reads .env
client = MiniMax(api_key="sk-xxx")    # parameter override
```

### Configuration

All configurable via `.env` or constructor parameters.

Priority: `parameter` > `.env` > `system env var` > `default value`

Configuration is read from constructor parameters or environment variables. The SDK does not auto-load `.env` files — users handle that in their own application if needed (e.g. `from dotenv import load_dotenv; load_dotenv()`).

| Parameter | Env Var | Default |
|-----------|---------|---------|
| `api_key` | `MINIMAX_API_KEY` | (required) |
| `base_url` | `MINIMAX_BASE_URL` | `https://api.minimax.io` |
| `timeout.connect` | `MINIMAX_TIMEOUT_CONNECT` | `5.0` |
| `timeout.read` | `MINIMAX_TIMEOUT_READ` | `600` |
| `timeout.write` | `MINIMAX_TIMEOUT_WRITE` | `600` |
| `timeout.pool` | `MINIMAX_TIMEOUT_POOL` | `600` |
| `max_retries` | `MINIMAX_MAX_RETRIES` | `2` |
| `poll_interval` | `MINIMAX_POLL_INTERVAL` | `5.0` |
| `poll_timeout` | `MINIMAX_POLL_TIMEOUT` | `600` |

### Resource Mounts

```python
client.speech    # Speech
client.voice     # Voice
client.video     # Video
client.image     # Image
client.music     # Music
client.files     # Files
```

---

## §3 SDK Methods → API Endpoints

18 distinct API endpoints, exposed as 26 SDK methods across 6 resources.

### Speech — `client.speech`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `.tts(text, model, ...)` | POST `/v1/t2a_v2` | Sync TTS, returns `AudioResponse` |
| `.tts_stream(text, model, ...)` | POST `/v1/t2a_v2` (stream) | Streaming TTS, yields `bytes` chunks (decoded from hex) |
| `.connect(model, ...)` | WSS `/ws/v1/t2a_v2` | WebSocket connection, returns `SpeechConnection` |
| `.async_create(text, model, ...)` | POST `/v1/t2a_async_v2` | Low-level: create long-text task |
| `.async_query(task_id)` | GET `/v1/query/t2a_async_query_v2` | Low-level: query task status |
| `.async_generate(text, model, ...)` | POST + auto poll | High-level: create + wait + return result |

### Voice — `client.voice`

`voice.upload_audio` delegates to `self._client.files.upload(file, purpose)` internally.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `.upload_audio(file, purpose="voice_clone")` | POST `/v1/files/upload` | Convenience: upload clone/prompt audio |
| `.clone(file_id, voice_id, ...)` | POST `/v1/voice_clone` | Clone a voice, returns `VoiceCloneResult` |
| `.design(prompt, preview_text)` | POST `/v1/voice_design` | Design voice from description, returns `VoiceDesignResult` |
| `.list(voice_type)` | POST `/v1/get_voice` | List voices (POST because API requires body filter), returns `VoiceList` |
| `.delete(voice_id, voice_type)` | POST `/v1/delete_voice` | Delete a voice, returns `None` |

### Video — `client.video`

High-level methods compose: `create()` → `query()` poll loop → `files.retrieve()`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `.text_to_video(prompt, model, ...)` | POST + poll + retrieve | T2V, auto polling, returns `VideoResult` |
| `.image_to_video(image, model, ...)` | POST + poll + retrieve | I2V, auto polling, returns `VideoResult` |
| `.frames_to_video(last_frame, ...)` | POST + poll + retrieve | FL2V, auto polling, returns `VideoResult` |
| `.subject_to_video(subject_reference, ...)` | POST + poll + retrieve | S2V, auto polling, returns `VideoResult` |
| `.create(...)` | POST `/v1/video_generation` | Low-level: create task only |
| `.query(task_id)` | GET `/v1/query/video_generation` | Low-level: query status |

### Image — `client.image`

Image generation is synchronous (blocking HTTP call, no polling).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `.generate(prompt, model, ...)` | POST `/v1/image_generation` | T2I/I2I. Pass optional `subject_reference: list[ImageSubjectReference]` for I2I mode. Returns `ImageResult` |

### Music — `client.music`

Music generation is synchronous (blocking HTTP call, no polling).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `.generate(model, prompt, lyrics, ...)` | POST `/v1/music_generation` | Generate music, returns `AudioResponse` |
| `.generate_stream(model, ...)` | POST `/v1/music_generation` (stream) | Streaming music, yields `bytes` chunks (decoded from hex) |
| `.generate_lyrics(mode, prompt, ...)` | POST `/v1/lyrics_generation` | Generate lyrics, returns `LyricsResult` |

### Files — `client.files`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `.upload(file, purpose)` | POST `/v1/files/upload` | Upload file. Valid purposes: `voice_clone`, `prompt_audio`, `t2a_async_input` |
| `.list(purpose)` | GET `/v1/files/list` | List files |
| `.retrieve(file_id)` | GET `/v1/files/retrieve` | Get file info + download URL (1hr expiry for video, 9hr for T2A async) |
| `.retrieve_content(file_id)` | GET `/v1/files/retrieve_content` | Download raw file content as `bytes` |
| `.delete(file_id, purpose)` | POST `/v1/files/delete` | Delete file. Valid purposes: `voice_clone`, `prompt_audio`, `t2a_async`, `t2a_async_input`, `video_generation` |

---

## §4 Return Types

### Shared Types

All types are Pydantic v2 models. `file_id` is `str` everywhere (MiniMax returns numeric IDs but they are used as opaque identifiers in API calls).

```python
class AudioResponse:
    data: bytes           # Decoded audio bytes (from hex)
    duration: float       # Milliseconds (float to avoid truncation)
    sample_rate: int
    format: str           # mp3, pcm, flac, wav
    size: int             # Bytes

    def save(self, path: str)
    def to_base64(self) -> str
    # __repr__ truncates data field to avoid printing massive byte strings

class TaskResult:
    task_id: str
    status: str
    file_id: str
    download_url: str
```

### Resource-Specific Types

```python
class VideoResult(TaskResult):
    video_width: int
    video_height: int

class ImageResult:
    id: str
    image_urls: list[str] | None       # Present when response_format="url"
    image_base64: list[str] | None     # Present when response_format="base64"
    success_count: int
    failed_count: int

class ImageSubjectReference:
    type: str             # Currently only "character"
    image_file: str       # Public URL or base64 data URL

class VoiceCloneResult:
    voice_id: str                      # Echo back for chaining
    demo_audio: AudioResponse | None   # Present when text+model are provided
    input_sensitive: dict

class VoiceDesignResult:
    voice_id: str
    trial_audio: AudioResponse

class VoiceInfo:
    voice_id: str
    voice_name: str | None             # Only for system voices
    description: list[str]
    created_time: str | None           # Only for cloned/generated voices

class VoiceList:
    system_voice: list[VoiceInfo]      # Populated when voice_type="system" or "all"
    voice_cloning: list[VoiceInfo]     # Populated when voice_type="voice_cloning" or "all"
    voice_generation: list[VoiceInfo]  # Populated when voice_type="voice_generation" or "all"

class LyricsResult:
    song_title: str
    style_tags: str
    lyrics: str

class FileInfo:
    file_id: str          # Unified as str everywhere
    bytes: int
    created_at: int
    filename: str
    purpose: str
    download_url: str | None
```

Principles:
- `base_resp` is never exposed — success means data, failure means exception
- Hex audio is always decoded — users receive `bytes` or `AudioResponse`
- `AudioResponse.__repr__` truncates `data` to avoid printing large byte strings
- `file_id` is `str` across all types for consistency
- URL expiration noted in docstrings (video retrieve: 1hr, image: 24hr, T2A async: 9hr)

---

## §5 Exception Hierarchy

```
MiniMaxError                          # Base class
├── AuthError                         # 1004, 2049
├── RateLimitError                    # 1002, 1039, 1041, 2045
├── InsufficientBalanceError          # 1008, 2056
├── ContentSafetyError                # 1026, 1027
│   ├── InputSafetyError              # 1026
│   └── OutputSafetyError             # 1027
├── InvalidParameterError             # 2013, 20132, 1042, 2037, 2048
├── TimeoutError                      # 1001
├── PollTimeoutError                  # SDK-side polling timeout
├── VoiceError
│   ├── VoiceCloneError               # 1043, 1044
│   ├── VoiceDuplicateError           # 2039
│   └── VoicePermissionError          # 2042
└── ServerError                       # 1000, 1024, 1033 (retryable)
```

All exceptions carry:
- `code: int` — original MiniMax status_code
- `message: str` — original status_msg
- `trace_id: str` — for debugging

### Error Code Mapping

| Code | MiniMax Name | Exception |
|------|-------------|-----------|
| 1000 | Unknown Error | `ServerError` |
| 1001 | Request Timeout | `TimeoutError` |
| 1002 | Rate Limit | `RateLimitError` |
| 1004 | Not Authorized | `AuthError` |
| 1008 | Insufficient Balance | `InsufficientBalanceError` |
| 1024 | Internal Error | `ServerError` |
| 1026 | Input Sensitive | `InputSafetyError` |
| 1027 | Output Sensitive | `OutputSafetyError` |
| 1033 | System Error | `ServerError` |
| 1039 | Token Limit | `RateLimitError` |
| 1041 | Connection Limit | `RateLimitError` |
| 1042 | Invisible Char Ratio | `InvalidParameterError` |
| 1043 | ASR Similarity Failed | `VoiceCloneError` |
| 1044 | Clone Prompt Failed | `VoiceCloneError` |
| 2013 | Invalid Parameters | `InvalidParameterError` |
| 20132 | Invalid Samples/Voice | `InvalidParameterError` |
| 2037 | Voice Duration Error | `InvalidParameterError` |
| 2039 | Voice Clone Duplicate | `VoiceDuplicateError` |
| 2042 | Access Denied | `VoicePermissionError` |
| 2045 | Rate Growth Limit | `RateLimitError` |
| 2048 | Prompt Audio Too Long | `InvalidParameterError` |
| 2049 | Invalid API Key | `AuthError` |
| 2056 | Usage Limit Exceeded | `InsufficientBalanceError` |

---

## §6 Retry & Polling

### Auto Retry

Retryable codes: `1000`, `1001`, `1002`, `1024`, `1033`

Strategy: Exponential backoff (1s → 2s → 4s → ...)
- For `1002` (Rate Limit): honor `Retry-After` header if present, fall back to exponential backoff otherwise.

Non-retryable codes throw immediately.

### Auto Polling

Applies to: Video (T2V/I2V/FL2V/S2V), T2A Async

```
create() → task_id
   ↓
loop:
   query(task_id) → status
   ├── Preparing/Queueing/Processing → sleep(poll_interval), continue
   ├── Success → file_id → retrieve(file_id) → return result
   └── Fail → raise MiniMaxError

exceed poll_timeout → raise PollTimeoutError
```

Configurable at method level:

```python
result = client.video.text_to_video(
    prompt="...",
    model="MiniMax-Hailuo-2.3",
    poll_interval=10.0,
    poll_timeout=1200.0
)
```

---

## §7 WebSocket T2A

### SpeechConnection

```python
class SpeechConnection:
    session_id: str

    def send(self, text: str) -> AudioResponse
    def send_stream(self, text: str) -> Iterator[bytes]
    def close()
```

### Usage

```python
with client.speech.connect(
    model="speech-2.8-hd",
    voice_setting={"voice_id": "English_expressive_narrator", "speed": 1.0},
    audio_setting={"format": "mp3", "sample_rate": 32000}
) as conn:
    audio = conn.send("Hello, how are you?")
    audio.save("hello.mp3")

# Async
async with client.speech.connect(model="speech-2.8-hd", ...) as conn:
    audio = await conn.send("Hello")
```

Key behaviors:
- `connect()` auto-sends `task_start` and waits for `task_started`
- `send()` sends `task_continue`, collects hex chunks, returns decoded `AudioResponse`
- `close()` sends `task_finish` and closes WebSocket
- 120-second idle timeout (API limitation)
- Context manager auto-closes on exit
- Authentication: API key passed via `Authorization` header during WebSocket upgrade handshake

Error handling:
- Connection drops (network error, server restart) raise `ConnectionError`
- No auto-reconnect — user must create a new connection
- `send_stream()` yields data up to point of failure, then raises exception
- `task_failed` events from server raise the corresponding `MiniMaxError`

---

## §8 Dependencies

```toml
[project]
name = "minimax-sdk"
requires-python = ">=3.10"

dependencies = [
    "httpx>=0.27",
    "websockets>=12.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "respx>=0.22",
]
```

---

## §9 Versioning

- SDK follows **semver** (e.g., `0.1.0`, `1.0.0`)
- API version is embedded in endpoint paths (`/v1/`)
- SDK supports one API version at a time
- Breaking changes from MiniMax API → SDK major version bump
