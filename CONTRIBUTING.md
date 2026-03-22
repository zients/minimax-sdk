# Contributing

Thanks for your interest in contributing to the MiniMax SDK!

## Setup

### Python

```bash
cd python
uv venv
uv pip install -e ".[dev]"
```

### TypeScript

```bash
cd typescript
npm install
```

## Running Tests

### Python

```bash
cd python
uv run ruff check src/          # lint
uv run ruff format --check src/ # format check
uv run pyright src/             # type check
uv run pytest tests/ --ignore=tests/integration -q  # unit tests
```

### TypeScript

```bash
cd typescript
npm run check      # type check
npm run lint       # eslint
npm run format:check  # prettier
npm test           # unit tests
npm run build      # build
```

## Pull Requests

- Target the `main` branch
- If you change one SDK, mirror the change in the other (Python <-> TypeScript)
- Add tests for new functionality
- Run lint, format, type check, and tests before submitting
- Use conventional commit messages (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)

## Integration Tests

Integration tests require a `MINIMAX_API_KEY` in `.env` at the repo root. They are not run in CI.

```bash
# Python
cd python && uv run pytest tests/integration/test_text.py -v

# TypeScript
cd typescript && npx vitest run --config /dev/null --test-timeout 600000 tests/integration/text.test.ts
```
