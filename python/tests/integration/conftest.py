"""Integration test configuration.

Loads .env file from the repo root so MINIMAX_API_KEY is available.
This is dev-only — the SDK itself never reads .env.
"""

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
