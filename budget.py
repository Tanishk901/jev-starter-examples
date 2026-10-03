"""Shared helpers: load the API key from .env and enforce a spending cap.

Every Jev call made by sorter.py or router.py is added up in spend.json.
A call is refused if it could push the total past LIMIT_USD, even in the worst case.
"""

import json
import os
from pathlib import Path

LIMIT_USD = 5.00
PRICE_PER_INPUT_TOKEN = 0.042 / 1_000_000  # Jev: $0.042 per million input tokens, output is free
MAX_TOKENS_PER_REQUEST = 64_000            # Jev's per-request limit, so the worst-case cost of one call

HERE = Path(__file__).parent
ENV_FILE = HERE / ".env"
SPEND_FILE = HERE / "spend.json"
PLACEHOLDER = "paste_your_key_here"


def load_api_key():
    """Read TYPESAFE_API_KEY from .env into the environment. Returns True if a real key is set."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "TYPESAFE_API_KEY":
                os.environ.setdefault("TYPESAFE_API_KEY", value.strip().strip('"'))
    key = os.environ.get("TYPESAFE_API_KEY", "")
    return bool(key) and key != PLACEHOLDER


class BudgetExceeded(Exception):
    pass


def _load():
    if SPEND_FILE.exists():
        return json.loads(SPEND_FILE.read_text(encoding="utf-8"))
    return {"input_tokens": 0, "requests": 0, "usd": 0.0}


def check():
    """Call before each request. Raises BudgetExceeded if the next call could cross the limit."""
    spent = _load()["usd"]
    worst_case = MAX_TOKENS_PER_REQUEST * PRICE_PER_INPUT_TOKEN
    if spent + worst_case > LIMIT_USD:
        raise BudgetExceeded(f"${spent:.4f} spent of ${LIMIT_USD:.2f} limit; stopping.")


def record(usage):
    """Call after each request with response.usage."""
    data = _load()
    data["input_tokens"] += usage.input_tokens
    data["requests"] += 1
    data["usd"] = data["input_tokens"] * PRICE_PER_INPUT_TOKEN
    SPEND_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def summary():
    data = _load()
    return (
        f"Total Jev spend so far: ${data['usd']:.6f} of ${LIMIT_USD:.2f} "
        f"({data['requests']} requests, {data['input_tokens']:,} input tokens)"
    )
