# MiniMax SDK for TypeScript

TypeScript SDK for [MiniMax](https://platform.minimax.io/) multimodal APIs -- Text, Speech, Voice, Video, Image, Music, and File management.

[![npm version](https://img.shields.io/npm/v/minimax-sdk.svg)](https://www.npmjs.com/package/minimax-sdk)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](https://nodejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5%2B-blue.svg)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-372%20passed-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-96.79%25-brightgreen.svg)](#testing)

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Resources](#resources)
  - [Text](#text----clienttext)
  - [Speech](#speech----clientspeech)
  - [Voice](#voice----clientvoice)
  - [Video](#video----clientvideo)
  - [Image](#image----clientimage)
  - [Music](#music----clientmusic)
  - [Files](#files----clientfiles)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [License](#license)

## Installation

```bash
npm install minimax-sdk
```

**Requirements:** Node.js 18+

## Quick Start

```typescript
import MiniMax from "minimax-sdk";

const client = new MiniMax({ apiKey: "your-api-key" });

// Text generation
const result = await client.text.create({
  model: "MiniMax-M2.7",
  messages: [{ role: "user", content: "Hello" }],
  maxTokens: 1024,
});
console.log(result.content[0].text);

// Text-to-Speech
const audio = await client.speech.tts({
  text: "Hello world",
  model: "speech-2.8-hd",
});
await audio.save("hello.mp3");

// Generate an image
const image = await client.image.generate("A cat on the moon", "image-01");
console.log(image.imageUrls);

// Generate a video (auto-polls until complete)
const video = await client.video.textToVideo("A sunrise over the ocean", "MiniMax-Hailuo-2.3");
console.log(video.downloadUrl);
```

## Configuration

### Constructor Options

```typescript
const client = new MiniMax({
  apiKey: "...",                         // required (or set MINIMAX_API_KEY env var)
  baseURL: "https://api.minimax.io",    // API base URL
  timeout: 600000,                       // request timeout in ms (default 600s)
  maxRetries: 2,                         // auto-retry on server/rate-limit errors
  pollInterval: 5,                       // async task polling interval (seconds)
  pollTimeout: 600,                      // async task max wait time (seconds)
  fetch: customFetch,                    // custom fetch implementation (optional)
});
```

### Environment Variables

Only `apiKey` and `baseURL` support environment variables. All other settings use constructor options with built-in defaults.

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MINIMAX_API_KEY` | *(required)* | Your MiniMax API key |
| `MINIMAX_BASE_URL` | `https://api.minimax.io` | API base URL |

```bash
export MINIMAX_API_KEY="your-api-key"
```

```typescript
import MiniMax from "minimax-sdk";

// Reads MINIMAX_API_KEY from environment automatically
const client = new MiniMax();
```

## Resources

### Text -- `client.text`

Uses MiniMax's Anthropic-compatible endpoint (`/anthropic/v1/messages`). Supports models: `MiniMax-M2.7`, `MiniMax-M2.5`, `MiniMax-M2.1`, `MiniMax-M2`, and their highspeed variants.

#### Basic Text Generation

```typescript
const result = await client.text.create({
  model: "MiniMax-M2.7",
  messages: [{ role: "user", content: "Hello" }],
  maxTokens: 1024,
});
// MiniMax models may return thinking blocks before text blocks
for (const block of result.content) {
  if (block.type === "text") {
    console.log(block.text);
  }
}
```

#### With System Prompt

```typescript
const result = await client.text.create({
  model: "MiniMax-M2.7",
  messages: [{ role: "user", content: "Explain quantum computing" }],
  maxTokens: 1024,
  system: "You are a physics professor. Explain concisely.",
  temperature: 0.7,
});
```

#### Streaming

```typescript
for await (const event of client.text.createStream({
  model: "MiniMax-M2.7",
  messages: [{ role: "user", content: "Write a short poem" }],
  maxTokens: 512,
})) {
  if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
    process.stdout.write(event.delta.text);
  }
}
```

#### Tool Use (Function Calling)

```typescript
const result = await client.text.create({
  model: "MiniMax-M2.7",
  messages: [{ role: "user", content: "What's the weather in Tokyo?" }],
  maxTokens: 1024,
  tools: [{
    name: "get_weather",
    description: "Get current weather for a location",
    input_schema: {
      type: "object",
      properties: { location: { type: "string" } },
      required: ["location"],
    },
  }],
});

for (const block of result.content) {
  if (block.type === "tool_use") {
    console.log(`Call ${block.name} with`, block.input);
  }
}
```

> **Note:** `tools`, `toolChoice`, and `thinking` are passed as raw objects to the Anthropic-compatible API. Their inner fields use the Anthropic API format (e.g. `input_schema`, `budget_tokens`).

#### Extended Thinking

```typescript
const result = await client.text.create({
  model: "MiniMax-M2.7",
  messages: [{ role: "user", content: "Solve: what is 127 * 389?" }],
  maxTokens: 4096,
  thinking: { type: "enabled", budget_tokens: 2048 },
});

for (const block of result.content) {
  if (block.type === "thinking") {
    console.log("Thinking:", block.thinking);
  } else if (block.type === "text") {
    console.log("Answer:", block.text);
  }
}
```

### Speech -- `client.speech`

#### Synchronous TTS

```typescript
const audio = await client.speech.tts({
  text: "Hello world",
  model: "speech-2.8-hd",
  voiceSetting: { voiceId: "English_expressive_narrator", speed: 1.0 },
  audioSetting: { format: "mp3", sampleRate: 32000 },
});
await audio.save("output.mp3");
```

#### Streaming TTS

```typescript
for await (const chunk of client.speech.ttsStream({
  text: "Hello world",
  model: "speech-2.8-hd",
  voiceSetting: { voiceId: "English_expressive_narrator" },
})) {
  // chunk is a Buffer of audio data
  player.write(chunk);
}
```

#### WebSocket TTS (Real-Time, Multi-Turn)

```typescript
const conn = await client.speech.connect({
  model: "speech-2.8-hd",
  voiceSetting: { voiceId: "English_expressive_narrator" },
});
try {
  const audio1 = await conn.send("Hello, how are you?");
  await audio1.save("chunk1.mp3");
  const audio2 = await conn.send("I'm doing great.");
  await audio2.save("chunk2.mp3");
} finally {
  await conn.close();
}
```

#### WebSocket Streaming TTS

```typescript
const conn = await client.speech.connect({
  model: "speech-2.8-hd",
  voiceSetting: { voiceId: "English_expressive_narrator" },
});
try {
  for await (const chunk of conn.sendStream("Hello, streaming world!")) {
    // chunk is a Buffer of audio data, arrives in real-time
    player.write(chunk);
  }
} finally {
  await conn.close();
}
```

#### Long-Text Async TTS (up to 100K characters)

```typescript
const result = await client.speech.asyncGenerate({
  text: "Very long text...",
  model: "speech-2.8-hd",
  voiceSetting: { voiceId: "English_expressive_narrator" },
});
console.log(result.downloadUrl);
```

For lower-level control, use `asyncCreate` and `asyncQuery` separately:

```typescript
const task = await client.speech.asyncCreate({
  text: "Very long text...",
  model: "speech-2.8-hd",
  voiceSetting: { voiceId: "English_expressive_narrator" },
});
const status = await client.speech.asyncQuery(String(task.task_id));
```

> **Note:** `asyncCreate` and `asyncQuery` return raw `Record<string, unknown>` responses with snake_case keys (e.g. `task.task_id`). The high-level `asyncGenerate` returns a typed `TaskResult` with camelCase keys (e.g. `result.downloadUrl`).

### Voice -- `client.voice`

> **Note:** `voice.clone` and `voice.design` require a [pay-as-you-go](https://platform.minimax.io/user-center/basic-information/interface-key) account with sufficient balance. They are not covered by the Token Plan. `voice.list` and `voice.delete` work with any account.

#### Clone a Voice

```typescript
const fileInfo = await client.voice.uploadAudio("reference.mp3");
const result = await client.voice.clone(fileInfo.fileId, "my-custom-voice");
```

#### Design a Voice from Description

```typescript
const result = await client.voice.design(
  "A warm, friendly male narrator",
  "Hello, welcome to our show.",
);
await result.trialAudio?.save("preview.mp3");
console.log(result.voiceId); // use this in TTS calls
```

#### List and Delete Voices

```typescript
const voices = await client.voice.list("voice_cloning");
await client.voice.delete("my-custom-voice", "voice_cloning");
```

### Video -- `client.video`

All high-level video methods automatically poll until the generation task completes and return a `VideoResult` with a temporary download URL.

#### Text to Video

```typescript
const result = await client.video.textToVideo(
  "A cat playing piano",
  "MiniMax-Hailuo-2.3",
  { duration: 6, resolution: "1080P" },
);
console.log(result.downloadUrl);
```

#### Image to Video

```typescript
const result = await client.video.imageToVideo(
  "https://example.com/photo.jpg",
  "MiniMax-Hailuo-2.3",
  { prompt: "The scene comes alive" },
);
```

#### First and Last Frame to Video

```typescript
const result = await client.video.framesToVideo(
  "https://example.com/end.jpg",
  {
    model: "MiniMax-Hailuo-02",
    firstFrameImage: "https://example.com/start.jpg",
  },
);
```

#### Subject Reference Video

```typescript
const result = await client.video.subjectToVideo(
  [{ type: "character", image: "https://example.com/face.jpg" }],
  { model: "S2V-01", prompt: "A person waving at the camera" },
);
```

#### Low-Level Control

```typescript
const task = await client.video.create({ model: "MiniMax-Hailuo-2.3", prompt: "..." });
const status = await client.video.query(String(task.task_id));
```

> **Note:** `create` and `query` return raw `Record<string, unknown>` responses with snake_case keys. The high-level methods (`textToVideo`, `imageToVideo`, etc.) return typed `VideoResult` with camelCase keys.

### Image -- `client.image`

#### Text to Image

```typescript
const result = await client.image.generate(
  "A futuristic city at sunset",
  "image-01",
  { aspectRatio: "16:9", n: 3 },
);
console.log(result.imageUrls);
```

#### Image to Image (with Subject Reference)

```typescript
const result = await client.image.generate(
  "A woman in a garden",
  "image-01",
  { subjectReference: [{ type: "character", imageFile: "https://example.com/face.jpg" }] },
);
```

#### Additional Parameters

```typescript
const result = await client.image.generate(
  "A beautiful landscape",
  "image-01",
  {
    responseFormat: "base64",    // "url" (default) or "base64"
    width: 1024,                 // explicit dimensions (mutually exclusive with aspectRatio)
    height: 768,
    seed: 42,                    // reproducibility
    n: 2,                        // number of images
    promptOptimizer: true,       // let the API optimize the prompt
  },
);
```

### Music -- `client.music`

#### Generate Music

```typescript
const audio = await client.music.generate("music-2.5+", {
  prompt: "Indie folk, melancholic mood",
  lyrics: "[Verse]\nWalking down the empty road\n[Chorus]\nBut I know the sun will rise",
});
await audio.save("song.mp3");
```

#### Generate with Streaming

```typescript
const chunks: Buffer[] = [];
for await (const chunk of client.music.generateStream("music-2.5+", {
  prompt: "Lo-fi hip hop beats",
  isInstrumental: true,
})) {
  chunks.push(chunk);
}
```

#### Generate Lyrics First, Then Music

```typescript
const lyrics = await client.music.generateLyrics("write_full_song", {
  prompt: "A cheerful summer love song",
});
console.log(lyrics.songTitle);
console.log(lyrics.lyrics);

const audio = await client.music.generate("music-2.5+", { lyrics: lyrics.lyrics });
await audio.save("summer.mp3");
```

### Files -- `client.files`

```typescript
// Upload a file
const fileInfo = await client.files.upload("audio.mp3", "voice_clone");
console.log(fileInfo.fileId);

// List files by purpose
const files = await client.files.list("voice_clone");

// Retrieve file metadata (includes a temporary download URL)
const info = await client.files.retrieve("123");
console.log(info.downloadUrl);

// Download raw file content
const content = await client.files.retrieveContent("123");

// Delete a file
await client.files.delete("123", "voice_clone");
```

## Error Handling

All errors extend `MiniMaxError` and carry structured error information:

- `code` -- the MiniMax API status code
- `message` -- human-readable error description
- `traceId` -- request trace identifier for debugging

### Error Hierarchy

| Error                      | Description                                       |
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

```typescript
import MiniMax, {
  RateLimitError,
  ContentSafetyError,
  AuthError,
  APITimeoutError,
  MiniMaxError,
} from "minimax-sdk";

const client = new MiniMax({ apiKey: "your-api-key" });

try {
  const result = await client.video.textToVideo("...", "MiniMax-Hailuo-2.3");
} catch (err) {
  if (err instanceof RateLimitError) {
    console.log("Rate limited after all retries");
  } else if (err instanceof ContentSafetyError) {
    console.log("Content safety violation");
  } else if (err instanceof AuthError) {
    console.log("Authentication failed");
  } else if (err instanceof APITimeoutError) {
    console.log("Request timed out");
  } else if (err instanceof MiniMaxError) {
    console.log(`Error ${err.code}: ${err.message} (traceId=${err.traceId})`);
  }
}
```

## Testing

```bash
# Unit tests (372 tests, ~0.4s)
npm test

# Type check
npm run check

# Lint
npm run lint

# Build
npm run build

# Integration tests (requires MINIMAX_API_KEY in ../.env)
npx vitest run --config /dev/null tests/integration/text.test.ts
npx vitest run --config /dev/null tests/integration/files.test.ts
npx vitest run --config /dev/null tests/integration/image.test.ts
npx vitest run --config /dev/null tests/integration/voice.test.ts
npx vitest run --config /dev/null tests/integration/music.test.ts
npx vitest run --config /dev/null tests/integration/video.test.ts
npx vitest run --config /dev/null tests/integration/speech.test.ts
```

## License

[MIT](../LICENSE)
