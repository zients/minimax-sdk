# MiniMax SDK

SDKs for MiniMax's multimodal APIs.

[![PyPI version](https://img.shields.io/pypi/v/minimax-sdk.svg)](https://pypi.org/project/minimax-sdk/)
[![npm version](https://img.shields.io/npm/v/minimax-sdk.svg)](https://www.npmjs.com/package/minimax-sdk)
[![Python](https://img.shields.io/pypi/pyversions/minimax-sdk.svg)](https://pypi.org/project/minimax-sdk/)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Supported APIs

| API | Capabilities |
|-----|-------------|
| Text | Chat completion, streaming, tool use, extended thinking (via Anthropic-compatible endpoint) |
| Speech | TTS (sync, streaming, WebSocket, async long-text) |
| Video | Text-to-video, image-to-video, first/last-frame, subject reference |
| Image | Text-to-image, image-to-image |
| Music | Generate, stream, lyrics |
| Voice | Clone, design, list, delete |
| Files | Upload, list, retrieve, download, delete |

## Language SDKs

| Language | Status | Path | Package |
|----------|--------|------|---------|
| Python | Available | [`python/`](python/) | [![PyPI](https://img.shields.io/pypi/v/minimax-sdk.svg)](https://pypi.org/project/minimax-sdk/) |
| TypeScript | Available | [`typescript/`](typescript/) | [![npm](https://img.shields.io/npm/v/minimax-sdk.svg)](https://www.npmjs.com/package/minimax-sdk) |

## Quick Start

### Python

```bash
pip install minimax-sdk
```

```python
from minimax_sdk import MiniMax

client = MiniMax(api_key="your-api-key")

# Text generation
result = client.text.create(
    model="MiniMax-M2.7",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=1024,
)
print(result.content[0].text)

# Text-to-Speech
audio = client.speech.tts(text="Hello world", model="speech-2.8-hd")
audio.save("hello.mp3")
```

See [python/README.md](python/README.md) for full documentation.

### TypeScript

```bash
npm install minimax-sdk
```

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
```

See [typescript/README.md](typescript/README.md) for full documentation.

## License

[MIT](LICENSE)
