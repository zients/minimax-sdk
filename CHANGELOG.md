# Changelog

## 0.1.2

- Fix TypeScript streaming hang when SSE data spans multiple TCP chunks
- Fix TypeScript stream line splitting to handle `\r\n` line endings
- Add pyright type checking to Python CI (0 errors)
- Add Prettier formatting to TypeScript CI
- Unify Python version to single source of truth (`pyproject.toml` via `importlib.metadata`)
- Add `CONTRIBUTING.md` and `CHANGELOG.md`

## 0.1.1

- Fix music generate default `outputFormat` from `url` to `hex` (align with MiniMax API default)
- Fix Python WebSocket TLS certificate validation (remove unsafe `CERT_NONE` bypass)
- Fix SSE parser multi-line `data:` concatenation per spec (TypeScript + Python)
- Fix TypeScript stream cancel: use `reader.cancel()` instead of `releaseLock()`
- Add retry backoff jitter to prevent thundering herd
- Add `py.typed` marker for PEP 561 typed package support
- Remove unused `_api_key` from Python `SpeechConnection`

## 0.1.0

- Initial release
- Python SDK (`zients-minimax-sdk` on PyPI)
- TypeScript SDK (`@zients/minimax-sdk` on npm)
- Supported APIs: Text, Speech, Voice, Video, Image, Music, Files
