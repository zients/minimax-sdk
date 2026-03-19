# MiniMax SDK for Python

Python SDK for [MiniMax](https://platform.minimax.io/) multimodal APIs -- Speech, Voice, Video, Image, Music, and File management.

[![PyPI version](https://img.shields.io/pypi/v/minimax-sdk.svg)](https://pypi.org/project/minimax-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/minimax-sdk.svg)](https://pypi.org/project/minimax-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Resources](#resources)
  - [Speech](#speech----clientspeech)
  - [Voice](#voice----clientvoice)
  - [Video](#video----clientvideo)
  - [Image](#image----clientimage)
  - [Music](#music----clientmusic)
  - [Files](#files----clientfiles)
- [Text Generation](#text-generation)
- [Async Support](#async-support)
- [Error Handling](#error-handling)
- [License](#license)

## Installation

```bash
pip install minimax-sdk
```

**Requirements:** Python 3.10+

## Quick Start

```python
from minimax_sdk import MiniMax

client = MiniMax(api_key="your-api-key")

# Text-to-Speech
audio = client.speech.tts(text="Hello world", model="speech-2.8-hd")
audio.save("hello.mp3")

# Generate an image
result = client.image.generate(prompt="A cat on the moon", model="image-01")
print(result.image_urls)

# Generate a video (auto-polls until complete)
result = client.video.text_to_video(prompt="A sunrise over the ocean", model="MiniMax-Hailuo-2.3")
print(result.download_url)
```

## Configuration

### Constructor Parameters

```python
client = MiniMax(
    api_key="...",                  # required (or set MINIMAX_API_KEY env var)
    base_url="https://api.minimax.io",  # API base URL
    timeout_connect=5.0,           # connection timeout (seconds)
    timeout_read=600.0,            # read timeout (seconds)
    timeout_write=600.0,           # write timeout (seconds)
    timeout_pool=600.0,            # pool timeout (seconds)
    max_retries=2,                 # auto-retry on server/rate-limit errors
    poll_interval=5.0,             # async task polling interval (seconds)
    poll_timeout=600.0,            # async task max wait time (seconds)
)
```

### Environment Variables

Only `api_key` and `base_url` support environment variables. All other settings use constructor parameters with built-in defaults.

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MINIMAX_API_KEY` | *(required)* | Your MiniMax API key |
| `MINIMAX_BASE_URL` | `https://api.minimax.io` | API base URL |

```bash
export MINIMAX_API_KEY="your-api-key"
```

```python
from minimax_sdk import MiniMax

# Reads MINIMAX_API_KEY from environment automatically
client = MiniMax()
```

## Resources

### Speech -- `client.speech`

#### Synchronous TTS

```python
audio = client.speech.tts(
    text="Hello world",
    model="speech-2.8-hd",
    voice_setting={"voice_id": "English_expressive_narrator", "speed": 1.0},
    audio_setting={"format": "mp3", "sample_rate": 32000},
)
audio.save("output.mp3")
```

#### Streaming TTS

```python
for chunk in client.speech.tts_stream(text="Hello world", model="speech-2.8-hd"):
    player.write(chunk)
```

#### WebSocket (Real-Time, Multi-Turn)

```python
with client.speech.connect(
    model="speech-2.8-hd",
    voice_setting={"voice_id": "English_expressive_narrator"},
) as conn:
    audio = conn.send("Hello, how are you?")
    audio.save("chunk1.mp3")
    audio = conn.send("I'm doing great.")
    audio.save("chunk2.mp3")
```

#### Long-Text Async TTS (up to 100K characters)

The high-level `async_generate` method creates a task, polls until completion, and returns the result with a download URL:

```python
result = client.speech.async_generate(
    text="Very long text...",
    model="speech-2.8-hd",
    voice_setting={"voice_id": "English_expressive_narrator"},
)
print(result.download_url)
```

For lower-level control, use `async_create` and `async_query` separately:

```python
task = client.speech.async_create(
    text="Very long text...",
    model="speech-2.8-hd",
    voice_setting={"voice_id": "English_expressive_narrator"},
)
task_id = task["task_id"]

# Poll manually
status = client.speech.async_query(task_id)
```

### Voice -- `client.voice`

#### Clone a Voice

```python
file_info = client.voice.upload_audio("reference.mp3")
result = client.voice.clone(file_id=file_info.file_id, voice_id="my-custom-voice")
```

#### Design a Voice from Description

```python
result = client.voice.design(
    prompt="A warm, friendly male narrator",
    preview_text="Hello, welcome to our show.",
)
result.trial_audio.save("preview.mp3")
print(result.voice_id)  # use this in TTS calls
```

#### List and Delete Voices

```python
voices = client.voice.list(voice_type="voice_cloning")
client.voice.delete(voice_id="my-custom-voice", voice_type="voice_cloning")
```

### Video -- `client.video`

All high-level video methods automatically poll until the generation task completes and return a `VideoResult` with a temporary download URL.

#### Text to Video

```python
result = client.video.text_to_video(
    prompt="A cat playing piano",
    model="MiniMax-Hailuo-2.3",
    duration=6,
    resolution="1080P",
)
print(result.download_url)
```

#### Image to Video

```python
result = client.video.image_to_video(
    first_frame_image="https://example.com/photo.jpg",
    prompt="The scene comes alive",
    model="MiniMax-Hailuo-2.3",
)
```

#### First and Last Frame to Video

```python
result = client.video.frames_to_video(
    last_frame_image="https://example.com/end.jpg",
    first_frame_image="https://example.com/start.jpg",
    model="MiniMax-Hailuo-02",
)
```

#### Subject Reference Video

```python
result = client.video.subject_to_video(
    subject_reference=[{"type": "character", "image": ["https://example.com/face.jpg"]}],
    prompt="A person waving at the camera",
    model="S2V-01",
)
```

#### Low-Level Control

```python
task = client.video.create(model="MiniMax-Hailuo-2.3", prompt="...")
status = client.video.query(task["task_id"])
```

### Image -- `client.image`

#### Text to Image

```python
result = client.image.generate(
    prompt="A futuristic city at sunset",
    model="image-01",
    aspect_ratio="16:9",
    n=3,
)
print(result.image_urls)
```

#### Image to Image (with Subject Reference)

```python
result = client.image.generate(
    prompt="A woman in a garden",
    model="image-01",
    subject_reference=[{"type": "character", "image_file": "https://example.com/face.jpg"}],
)
```

#### Additional Parameters

```python
result = client.image.generate(
    prompt="...",
    model="image-01",
    response_format="base64",    # "url" (default) or "base64"
    width=1024,                  # explicit dimensions (mutually exclusive with aspect_ratio)
    height=768,
    seed=42,                     # reproducibility
    n=2,                         # number of images
    prompt_optimizer=True,       # let the API optimize the prompt
)
```

### Music -- `client.music`

#### Generate Music

```python
audio = client.music.generate(
    model="music-2.5+",
    prompt="Indie folk, melancholic mood",
    lyrics="[Verse]\nWalking down the empty road\n[Chorus]\nBut I know the sun will rise",
)
audio.save("song.mp3")
```

#### Generate with Streaming

```python
chunks = []
for chunk in client.music.generate_stream(
    model="music-2.5+",
    prompt="Lo-fi hip hop beats",
    is_instrumental=True,
):
    chunks.append(chunk)
```

#### Generate Lyrics First, Then Music

```python
lyrics = client.music.generate_lyrics(
    mode="write_full_song",
    prompt="A cheerful summer love song",
)
print(lyrics.lyrics)

audio = client.music.generate(model="music-2.5+", lyrics=lyrics.lyrics)
audio.save("summer.mp3")
```

#### Instrumental Music

```python
audio = client.music.generate(
    model="music-2.5+",
    prompt="Lo-fi hip hop beats",
    is_instrumental=True,
)
```

### Files -- `client.files`

```python
# Upload a file
file_info = client.files.upload("audio.mp3", purpose="voice_clone")

# List files by purpose
files = client.files.list(purpose="voice_clone")

# Retrieve file metadata (includes a temporary download URL)
info = client.files.retrieve(file_id="123")
print(info.download_url)

# Download raw file content
content = client.files.retrieve_content(file_id="123")

# Delete a file
client.files.delete(file_id="123", purpose="voice_clone")
```

## Text Generation

Text generation uses the [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) with MiniMax's Anthropic-compatible endpoint:

```bash
pip install anthropic
```

```python
import anthropic

client = anthropic.Anthropic(
    api_key="your-minimax-api-key",
    base_url="https://api.minimax.io/anthropic",
)

message = client.messages.create(
    model="MiniMax-M2.5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
print(message.content[0].text)
```

## Async Support

Every resource method has an async counterpart via `AsyncMiniMax`. The API is identical -- just add `await`:

```python
import asyncio
from minimax_sdk import AsyncMiniMax

async def main():
    client = AsyncMiniMax(api_key="your-api-key")

    # All methods are awaitable
    audio = await client.speech.tts(text="Hello", model="speech-2.8-hd")
    audio.save("hello.mp3")

    result = await client.video.text_to_video(
        prompt="A sunrise over the ocean",
        model="MiniMax-Hailuo-2.3",
    )
    print(result.download_url)

    # Async context manager support
    async with AsyncMiniMax(api_key="your-api-key") as client:
        result = await client.image.generate(prompt="A cat", model="image-01")

    # Async WebSocket
    async with client.speech.connect(
        model="speech-2.8-hd",
        voice_setting={"voice_id": "English_expressive_narrator"},
    ) as conn:
        audio = await conn.send("Hello!")
        audio.save("hello.mp3")

    # Async streaming music
    async for chunk in client.music.generate_stream(
        model="music-2.5+",
        prompt="Ambient electronic",
        is_instrumental=True,
    ):
        process(chunk)

    await client.close()

asyncio.run(main())
```

Both `MiniMax` and `AsyncMiniMax` support context managers for automatic resource cleanup:

```python
# Sync
with MiniMax(api_key="your-api-key") as client:
    audio = client.speech.tts(text="Hello", model="speech-2.8-hd")

# Async
async with AsyncMiniMax(api_key="your-api-key") as client:
    audio = await client.speech.tts(text="Hello", model="speech-2.8-hd")
```

## Error Handling

All exceptions inherit from `MiniMaxError` and carry structured error information:

- `code` -- the MiniMax API status code
- `message` -- human-readable error description
- `trace_id` -- request trace identifier for debugging

### Exception Hierarchy

| Exception                  | Description                                       |
|----------------------------|---------------------------------------------------|
| `MiniMaxError`             | Base class for all SDK errors                     |
| `AuthError`                | Invalid API key (codes 1004, 2049)                |
| `RateLimitError`           | Rate limit exceeded; auto-retried first           |
| `InsufficientBalanceError` | Account balance too low (codes 1008, 2056)        |
| `ContentSafetyError`       | Content safety violation (base class)             |
| `InputSafetyError`         | Input triggered safety filter (code 1026)         |
| `OutputSafetyError`        | Output triggered safety filter (code 1027)        |
| `InvalidParameterError`    | Invalid request parameters                        |
| `APITimeoutError`          | Server-side request timeout (code 1001)           |
| `PollTimeoutError`         | SDK-side polling timeout (task did not complete)   |
| `ServerError`              | Server-side error, typically retryable            |
| `VoiceError`               | Base class for voice-related errors               |
| `VoiceCloneError`          | Voice cloning failed                              |
| `VoiceDuplicateError`      | Duplicate voice clone attempt                     |
| `VoicePermissionError`     | Voice access denied                               |

### Example

```python
from minimax_sdk import MiniMax, RateLimitError, ContentSafetyError, AuthError, APITimeoutError, MiniMaxError

client = MiniMax(api_key="your-api-key")

try:
    result = client.video.text_to_video(prompt="...", model="MiniMax-Hailuo-2.3")
except RateLimitError:
    # Auto-retried up to max_retries times before being raised
    print("Rate limited after all retries")
except ContentSafetyError:
    # Input or output content violated safety policy
    print("Content safety violation")
except AuthError:
    # Invalid API key
    print("Authentication failed")
except APITimeoutError:
    # Server-side timeout
    print("Request timed out")
except MiniMaxError as e:
    # Catch-all for any MiniMax error
    print(f"Error {e.code}: {e.message} (trace_id={e.trace_id})")
```

## License

[MIT](../LICENSE)
